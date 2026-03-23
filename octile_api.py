"""
Octile puzzle game scoreboard API with anti-cheat verification.

Uses a **separate SQLite database** (octile.db) to store puzzle solve scores,
isolated from the main XSW cache and analytics databases.

Encoding Reference
==================

Base-92 Alphabet (P92)
----------------------
Printable ASCII 33–126 excluding ' (39) and \\ (92) → 92 characters:
  !"#$%&()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{|}~

Puzzle Data Encoding (3 chars per puzzle)
-----------------------------------------
Each puzzle defines 6 grey cells: 1×grey1 + 2×grey2 + 3×grey3 on an 8×8 board.

Encoding:
  combined = g1_pos × 10752 + g2_placement × 96 + g3_placement
  → 3 base-92 chars (little-endian): c0 + c1×92 + c2×92²

Where:
  - g1_pos: cell index 0–63
  - g2_placement (0–111): grey2 is a 1×2 domino
      0–55:  horizontal — row = idx÷7, col = idx%7, cells = (row×8+col, +1)
      56–111: vertical  — row = (idx-56)÷8, col = (idx-56)%8, cells = (row×8+col, +8)
  - g3_placement (0–95): grey3 is a 1×3 tromino
      0–47:  horizontal — row = idx÷6, col = idx%6, cells = (row×8+col, +1, +2)
      48–95: vertical  — row = (idx-48)÷8, col = (idx-48)%8, cells = (row×8+col, +8, +16)

Max combined = 63 × 10752 + 111 × 96 + 95 = 688,031 < 92³ = 778,688 ✓

Solution Encoding (27 chars, compact format)
--------------------------------------------
Encodes only the 58 non-grey cells (grey positions are known from puzzle data).

8 player piece IDs mapped to indices 0–7:
  0=r1(red1), 1=r2(red2), 2=w1(white1), 3=w2(white2),
  4=b1(blue1), 5=b2(blue2), 6=y1(yel1), 7=y2(yel2)

The 58 values (3 bits each) are split into 4 groups:
  Group 0: 15 cells → 45 bits → 7 base-92 chars (92⁷ > 2⁴⁵ ✓)
  Group 1: 15 cells → 45 bits → 7 base-92 chars
  Group 2: 15 cells → 45 bits → 7 base-92 chars
  Group 3: 13 cells → 39 bits → 6 base-92 chars (92⁶ > 2³⁹ ✓)
  Total: 7+7+7+6 = 27 chars

Each group encodes as little-endian mixed-radix:
  n = val[0] + val[1]×8 + val[2]×64 + ... (big end first in loop)
  chars: n%92, (n÷92)%92, ...

Cells are visited in order 0–63, skipping grey cells.

Legacy Format (128 chars)
-------------------------
64 × 2-char piece IDs: g1/g2/g3/r1/r2/w1/w2/b1/b2/y1/y2
Still accepted for backward compatibility.
"""

import hashlib
import hmac
import os
import time as _time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Index,
    and_,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import text as sql_text

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Puzzle data and verification constants
# ---------------------------------------------------------------------------
# Base-92 alphabet: printable ASCII 33-126, excluding ' (39) and \ (92)
P92 = '!"#$%&()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{|}~'
P92_MAP = {c: i for i, c in enumerate(P92)}

# Loaded lazily from puzzle_data.py to keep this file readable
_PUZZLE_DATA: str | None = None
PUZZLE_COUNT = 11378


def _get_puzzle_data() -> str:
    global _PUZZLE_DATA
    if _PUZZLE_DATA is None:
        from octile_puzzle_data import PUZZLE_DATA
        _PUZZLE_DATA = PUZZLE_DATA
    return _PUZZLE_DATA


# Piece definitions: short_id -> (cell_count, valid_orientations as (rows, cols))
PIECE_DEFS: dict[str, tuple[int, list[tuple[int, int]]]] = {
    "g1": (1, [(1, 1)]),
    "g2": (2, [(1, 2), (2, 1)]),
    "g3": (3, [(1, 3), (3, 1)]),
    "r1": (6, [(2, 3), (3, 2)]),
    "r2": (4, [(1, 4), (4, 1)]),
    "w1": (5, [(1, 5), (5, 1)]),
    "w2": (4, [(2, 2)]),
    "b1": (10, [(2, 5), (5, 2)]),
    "b2": (12, [(3, 4), (4, 3)]),
    "y1": (9, [(3, 3)]),
    "y2": (8, [(2, 4), (4, 2)]),
}

ALL_PIECE_IDS = set(PIECE_DEFS.keys())
GREY_IDS = {"g1", "g2", "g3"}
PLAYER_IDS = ALL_PIECE_IDS - GREY_IDS


def decode_puzzle(index: int) -> list[int]:
    """Decode puzzle at 0-based index from base-92 encoded data.

    Each puzzle is 3 base-92 chars encoding a combined index:
        combined = g1_pos * 10752 + g2_placement * 96 + g3_placement

    Grey2 placements (0-111):
        0-55: horizontal (row*7 + col, cell at row*8+col and +1)
        56-111: vertical ((idx-56)//8 = row, (idx-56)%8 = col, cell at row*8+col and +8)

    Grey3 placements (0-95):
        0-47: horizontal (row*6 + col, cells at row*8+col, +1, +2)
        48-95: vertical ((idx-48)//8 = row, (idx-48)%8 = col, cells at row*8+col, +8, +16)

    Returns [g1, g2a, g2b, g3a, g3b, g3c] as cell indices (0-63).
    """
    data = _get_puzzle_data()
    o = index * 3
    n = P92_MAP[data[o]] + P92_MAP[data[o + 1]] * 92 + P92_MAP[data[o + 2]] * 92 * 92

    g3_idx = n % 96
    g2_idx = (n // 96) % 112
    g1 = n // 10752

    # Decode grey2
    if g2_idx < 56:
        r, c = divmod(g2_idx, 7)
        g2a = r * 8 + c
        g2b = g2a + 1
    else:
        i = g2_idx - 56
        r, c = divmod(i, 8)
        g2a = r * 8 + c
        g2b = g2a + 8

    # Decode grey3
    if g3_idx < 48:
        r, c = divmod(g3_idx, 6)
        g3a = r * 8 + c
        g3b = g3a + 1
        g3c = g3a + 2
    else:
        i = g3_idx - 48
        r, c = divmod(i, 8)
        g3a = r * 8 + c
        g3b = g3a + 8
        g3c = g3a + 16

    return [g1, g2a, g2b, g3a, g3b, g3c]


def _cells_form_rectangle(
    cells: list[tuple[int, int]], valid_sizes: list[tuple[int, int]]
) -> bool:
    """Check if cells form a solid rectangle matching one of valid_sizes."""
    rows = [r for r, c in cells]
    cols = [c for r, c in cells]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    h = max_r - min_r + 1
    w = max_c - min_c + 1
    if (h, w) not in valid_sizes:
        return False
    if len(cells) != h * w:
        return False
    expected = {(min_r + dr, min_c + dc) for dr in range(h) for dc in range(w)}
    return set(cells) == expected


# Piece ID mappings for compact 27-char solution format
_SOL_PIECES = ["r1", "r2", "w1", "w2", "b1", "b2", "y1", "y2"]
_SOL_IDX = {pid: i for i, pid in enumerate(_SOL_PIECES)}


def _decode_compact_solution(
    solution_str: str, grey_cells: set[int]
) -> list[str] | None:
    """Decode a 27-char base-92 compact solution into a 64-cell board.

    Encoding: 58 non-grey cells, each with piece index 0-7 (3 bits).
    Grouped as 15+15+15+13 cells → 7+7+7+6 = 27 base-92 chars.
    Cells are visited in order 0-63, skipping grey cells.

    Returns list of 64 piece short-IDs (g1/g2/g3 for grey, r1/r2/w1/w2/b1/b2/y1/y2
    for player pieces), or None on decode error.
    """
    if len(solution_str) != 27:
        return None
    for c in solution_str:
        if c not in P92_MAP:
            return None

    groups = [15, 15, 15, 13]
    char_counts = [7, 7, 7, 6]
    board: list[str | None] = [None] * 64
    pos = 0  # position in solution string
    ci = 0   # cell index 0-63

    for g in range(4):
        # Decode base-92 group → big integer
        n = 0
        for i in range(char_counts[g] - 1, -1, -1):
            n = n * 92 + P92_MAP[solution_str[pos + i]]
        pos += char_counts[g]

        # Extract piece indices
        for _ in range(groups[g]):
            while ci < 64 and ci in grey_cells:
                ci += 1
            if ci >= 64:
                return None
            board[ci] = _SOL_PIECES[n % 8]
            n //= 8
            ci += 1

    return board  # type: ignore[return-value]


def verify_solution(puzzle_number: int, solution_str: str) -> tuple[bool, str | None]:
    """Verify a solution string against a puzzle. Returns (ok, error_msg).

    Accepts two formats:
    - 128-char legacy: 64 × 2-char piece IDs (g1/g2/g3/r1/r2/w1/w2/b1/b2/y1/y2)
    - 27-char compact: base-92 encoded non-grey cells only (see _decode_compact_solution)
    """
    if not isinstance(solution_str, str) or len(solution_str) not in (27, 128):
        return False, "solution must be 27 or 128 characters"

    puzzle_cells = decode_puzzle(puzzle_number - 1)
    grey_cell_set = set(puzzle_cells)

    if len(solution_str) == 27:
        # --- Compact format ---
        board = _decode_compact_solution(solution_str, grey_cell_set)
        if board is None:
            return False, "failed to decode compact solution"

        # Fill in grey cells
        board[puzzle_cells[0]] = "g1"
        board[puzzle_cells[1]] = "g2"
        board[puzzle_cells[2]] = "g2"
        board[puzzle_cells[3]] = "g3"
        board[puzzle_cells[4]] = "g3"
        board[puzzle_cells[5]] = "g3"

        # Convert flat board to piece_cells for validation
        grid = board
    else:
        # --- Legacy 128-char format ---
        grid = [solution_str[i : i + 2] for i in range(0, 128, 2)]

    # Check all IDs are valid
    for pid in grid:
        if pid not in ALL_PIECE_IDS:
            return False, f"invalid piece ID: {pid}"

    # Group cells by piece ID
    piece_cells: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for idx, pid in enumerate(grid):
        r, c = divmod(idx, 8)
        piece_cells[pid].append((r, c))

    # Check all 11 pieces present
    if set(piece_cells.keys()) != ALL_PIECE_IDS:
        missing = ALL_PIECE_IDS - set(piece_cells.keys())
        return False, f"missing pieces: {missing}"

    # Check cell counts and shapes
    for pid, cells in piece_cells.items():
        expected_count, valid_sizes = PIECE_DEFS[pid]
        if len(cells) != expected_count:
            return False, f"{pid}: expected {expected_count} cells, got {len(cells)}"
        if not _cells_form_rectangle(cells, valid_sizes):
            return False, f"{pid}: cells don't form valid rectangle"

    # Check grey pieces at correct positions
    g1_r, g1_c = divmod(puzzle_cells[0], 8)
    if piece_cells["g1"] != [(g1_r, g1_c)]:
        return False, "grey1 not at correct position"

    g2_expected = {divmod(ci, 8) for ci in puzzle_cells[1:3]}
    if set(piece_cells["g2"]) != g2_expected:
        return False, "grey2 not at correct positions"

    g3_expected = {divmod(ci, 8) for ci in puzzle_cells[3:6]}
    if set(piece_cells["g3"]) != g3_expected:
        return False, "grey3 not at correct positions"

    return True, None


# ---------------------------------------------------------------------------
# Separate declarative base — octile tables live in their own DB
# ---------------------------------------------------------------------------
OctileBase = declarative_base()


class OctileScore(OctileBase):
    """A single puzzle solve score entry."""

    __tablename__ = "octile_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    puzzle_number = Column(Integer, nullable=False, index=True)
    resolve_time = Column(Float, nullable=False)  # seconds
    browser_uuid = Column(String, nullable=False, index=True)
    timestamp_utc = Column(DateTime, nullable=True)  # legacy, nullable for new clients

    # Server-extracted client info
    client_ip = Column(String, nullable=True)
    client_host = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    forwarded_for = Column(String, nullable=True)
    origin = Column(String, nullable=True)
    real_ip = Column(String, nullable=True)

    # Legacy client-provided device info (no longer sent by new clients)
    os = Column(String, nullable=True)
    browser = Column(String, nullable=True)

    # Anti-cheat fields
    solution = Column(String, nullable=True)  # 27-char compact or 128-char legacy
    flagged = Column(Integer, default=0)  # 0=normal, 1=flagged for review

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    __table_args__ = (
        Index("idx_octile_puzzle_time", "puzzle_number", "resolve_time"),
        Index("idx_octile_uuid_puzzle", "browser_uuid", "puzzle_number"),
        Index("idx_octile_uuid_created", "browser_uuid", "created_at"),
    )

    def __repr__(self):
        return (
            f"<OctileScore(puzzle={self.puzzle_number}, "
            f"time={self.resolve_time}, uuid='{self.browser_uuid}')>"
        )


# ---------------------------------------------------------------------------
# Database management (separate from main db_models and analytics)
# ---------------------------------------------------------------------------
_engine = None
_SessionLocal = None


def init_db(db_url: str = None):
    """Initialize the Octile scoreboard database (separate SQLite file)."""
    global _engine, _SessionLocal

    if db_url is None:
        db_path = os.getenv("OCTILE_DB_PATH", "octile.db")
        db_url = f"sqlite:///{db_path}"

    _engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    OctileBase.metadata.create_all(bind=_engine)

    # Migrate existing tables: add new columns if missing
    _migrate_db()

    # Enable WAL mode for file-based SQLite
    if db_url.startswith("sqlite") and ":memory:" not in db_url:
        with _engine.connect() as conn:
            conn.execute(sql_text("PRAGMA journal_mode=WAL"))
            conn.execute(sql_text("PRAGMA synchronous=NORMAL"))
            conn.commit()

    print(f"[Octile] Database initialized: {db_url}")


def _migrate_db():
    """Add new columns to existing tables (safe to run multiple times)."""
    migrations = [
        "ALTER TABLE octile_scores ADD COLUMN solution TEXT",
        "ALTER TABLE octile_scores ADD COLUMN flagged INTEGER DEFAULT 0",
    ]
    with _engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(sql_text(sql))
            except Exception:
                pass  # Column already exists
        conn.commit()


def get_session() -> Session:
    """Get a new Octile database session."""
    if _SessionLocal is None:
        raise RuntimeError(
            "Octile DB not initialized. Call octile_api.init_db() first."
        )
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ScoreSubmitRequest(BaseModel):
    puzzle_number: int
    resolve_time: float
    browser_uuid: str
    solution: Optional[str] = None  # 27-char compact or 128-char legacy
    # Legacy fields (accepted but ignored during transition)
    timestamp_utc: Optional[str] = None
    os: Optional[str] = None
    browser: Optional[str] = None


class ScoreResponse(BaseModel):
    id: int
    puzzle_number: int
    resolve_time: float
    browser_uuid: str
    created_at: str
    timestamp_utc: str = ""  # legacy alias for created_at (old clients read this)
    flagged: int = 0


class ScoreboardResponse(BaseModel):
    puzzle_number: Optional[int] = None
    total: int
    scores: list[ScoreResponse]


class PuzzleStats(BaseModel):
    puzzle_number: int
    total_scores: int
    unique_players: int
    best_time: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _score_to_response(score: OctileScore) -> ScoreResponse:
    created = score.created_at.isoformat() if score.created_at else ""
    return ScoreResponse(
        id=score.id,
        puzzle_number=score.puzzle_number,
        resolve_time=score.resolve_time,
        browser_uuid=score.browser_uuid,
        created_at=created,
        timestamp_utc=created,  # legacy alias so old clients can sort by this
        flagged=score.flagged or 0,
    )


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp, handling Z suffix."""
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


def _extract_client_info(request: Request) -> dict:
    """Extract client info from request headers."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else ""
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    return {
        "client_ip": client_ip,
        "client_host": request.headers.get("Host"),
        "user_agent": request.headers.get("User-Agent"),
        "forwarded_for": forwarded_for or None,
        "origin": request.headers.get("Origin"),
        "real_ip": request.headers.get("X-Real-IP"),
    }


# HMAC secret shared with Cloudflare Worker (optional — skip if not set)
_WORKER_HMAC_SECRET = os.getenv("WORKER_HMAC_SECRET", "")
_WORKER_HMAC_MAX_AGE = 300  # reject signatures older than 5 minutes


def _verify_worker_signature(request: Request, body_bytes: bytes) -> bool:
    """Verify HMAC signature from Cloudflare Worker. Returns True if valid."""
    if not _WORKER_HMAC_SECRET:
        return True  # not configured, skip verification

    signature = request.headers.get("X-Worker-Signature")
    timestamp = request.headers.get("X-Worker-Timestamp")
    if not signature or not timestamp:
        return True  # no signature headers = direct request, allow through

    # Reject stale signatures
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(_time.time() - ts) > _WORKER_HMAC_MAX_AGE:
        return False

    # Verify HMAC(body + timestamp, secret)
    message = body_bytes.decode("utf-8", errors="replace") + timestamp
    expected = hmac.new(
        _WORKER_HMAC_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).digest()

    import base64

    try:
        received = base64.b64decode(signature)
    except Exception:
        return False

    return hmac.compare_digest(expected, received)


def _check_rate_limit(session: Session, browser_uuid: str) -> bool:
    """Return True if the UUID has submitted within the last 30 seconds."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)
    recent = (
        session.query(OctileScore)
        .filter(
            OctileScore.browser_uuid == browser_uuid,
            OctileScore.created_at >= cutoff,
        )
        .first()
    )
    return recent is not None


def _check_anomalies(session: Session, browser_uuid: str) -> bool:
    """Return True if this UUID shows suspicious patterns (flag, don't reject)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

    # Check 1: More than 50 scores in the last hour
    hour_count = (
        session.query(func.count(OctileScore.id))
        .filter(
            OctileScore.browser_uuid == browser_uuid,
            OctileScore.created_at >= cutoff,
        )
        .scalar()
    )
    if hour_count > 50:
        return True

    # Check 2: Average resolve_time < 20s over 10+ solves
    stats = (
        session.query(
            func.count(OctileScore.id).label("cnt"),
            func.avg(OctileScore.resolve_time).label("avg_time"),
        )
        .filter(OctileScore.browser_uuid == browser_uuid)
        .first()
    )
    if stats and stats.cnt >= 10 and stats.avg_time < 20:
        return True

    return False


# ---------------------------------------------------------------------------
# Router and endpoints
# ---------------------------------------------------------------------------
octile_router = APIRouter(prefix="/octile")


@octile_router.post("/score")
async def submit_score(request: Request):
    """Submit a puzzle solve score."""

    # --- Worker HMAC verification (Layer 0) --- disabled for now
    # raw_body = await request.body()
    # if not _verify_worker_signature(request, raw_body):
    #     return JSONResponse(
    #         status_code=403,
    #         content={"detail": "invalid or missing worker signature"},
    #     )

    raw_body = await request.body()
    try:
        body = ScoreSubmitRequest.model_validate_json(raw_body)
    except Exception:
        return JSONResponse(
            status_code=422,
            content={"detail": "invalid request body"},
        )

    # --- Validation (Layer 2) ---
    if not (1 <= body.puzzle_number <= PUZZLE_COUNT):
        return JSONResponse(
            status_code=400,
            content={"detail": f"puzzle_number must be 1–{PUZZLE_COUNT}"},
        )

    if body.resolve_time < 10:
        return JSONResponse(
            status_code=400,
            content={"detail": "resolve_time too fast (minimum 10s)"},
        )

    if body.resolve_time > 86400:
        return JSONResponse(
            status_code=400,
            content={"detail": "resolve_time too large (maximum 24h)"},
        )

    # --- Solution verification (Layer 3) ---
    if body.solution is not None:
        ok, err = verify_solution(body.puzzle_number, body.solution)
        if not ok:
            return JSONResponse(
                status_code=400,
                content={"detail": f"invalid solution: {err}"},
            )

    client_info = _extract_client_info(request)

    session = get_session()
    try:
        # --- Rate limiting ---
        if _check_rate_limit(session, body.browser_uuid):
            return JSONResponse(
                status_code=429,
                content={"detail": "too many submissions, try again in 30s"},
            )

        # --- Anomaly detection (Layer 4) ---
        flagged = 1 if _check_anomalies(session, body.browser_uuid) else 0

        # Parse legacy timestamp if provided, default to server time
        timestamp = datetime.now(timezone.utc)
        if body.timestamp_utc:
            try:
                timestamp = _parse_timestamp(body.timestamp_utc)
            except (ValueError, TypeError):
                pass

        score = OctileScore(
            puzzle_number=body.puzzle_number,
            resolve_time=body.resolve_time,
            browser_uuid=body.browser_uuid,
            timestamp_utc=timestamp,
            os=body.os,
            browser=body.browser,
            solution=body.solution,
            flagged=flagged,
            **client_info,
        )
        session.add(score)
        session.commit()
        session.refresh(score)
        return JSONResponse(
            status_code=201,
            content=_score_to_response(score).model_dump(),
        )
    finally:
        session.close()


@octile_router.get("/scoreboard")
def get_scoreboard(
    puzzle: Optional[int] = None,
    uuid: Optional[str] = None,
    best: bool = True,
    limit: int = 50,
    offset: int = 0,
):
    """Get the scoreboard. Defaults to best score per player per puzzle."""
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)

    session = get_session()
    try:
        if best:
            # Subquery: best (min) resolve_time per (browser_uuid, puzzle_number)
            subq = session.query(
                OctileScore.browser_uuid,
                OctileScore.puzzle_number,
                func.min(OctileScore.resolve_time).label("best_time"),
            ).group_by(OctileScore.browser_uuid, OctileScore.puzzle_number)
            if puzzle is not None:
                subq = subq.filter(OctileScore.puzzle_number == puzzle)
            if uuid is not None:
                subq = subq.filter(OctileScore.browser_uuid == uuid)
            subq = subq.subquery()

            query = session.query(OctileScore).join(
                subq,
                and_(
                    OctileScore.browser_uuid == subq.c.browser_uuid,
                    OctileScore.puzzle_number == subq.c.puzzle_number,
                    OctileScore.resolve_time == subq.c.best_time,
                ),
            )
        else:
            query = session.query(OctileScore)
            if puzzle is not None:
                query = query.filter(OctileScore.puzzle_number == puzzle)
            if uuid is not None:
                query = query.filter(OctileScore.browser_uuid == uuid)

        total = query.count()
        scores = (
            query.order_by(OctileScore.resolve_time.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return ScoreboardResponse(
            puzzle_number=puzzle,
            total=total,
            scores=[_score_to_response(s) for s in scores],
        )
    finally:
        session.close()


@octile_router.get("/puzzles")
def get_puzzles():
    """List puzzles that have scores, with stats."""
    session = get_session()
    try:
        rows = (
            session.query(
                OctileScore.puzzle_number,
                func.count(OctileScore.id).label("total_scores"),
                func.count(func.distinct(OctileScore.browser_uuid)).label(
                    "unique_players"
                ),
                func.min(OctileScore.resolve_time).label("best_time"),
            )
            .group_by(OctileScore.puzzle_number)
            .order_by(OctileScore.puzzle_number.asc())
            .all()
        )
        return [
            PuzzleStats(
                puzzle_number=r.puzzle_number,
                total_scores=r.total_scores,
                unique_players=r.unique_players,
                best_time=r.best_time,
            )
            for r in rows
        ]
    finally:
        session.close()
