"""
Octile puzzle game scoreboard API with anti-cheat verification.

Uses a **separate SQLite database** (octile.db) to store puzzle solve scores,
isolated from the main XSW cache and analytics databases.
"""

import os
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
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
B64_MAP = {c: i for i, c in enumerate(B64)}

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
    """Decode puzzle at 0-based index. Returns [g1, g2a, g2b, g3a, g3b, g3c]."""
    data = _get_puzzle_data()
    off = index * 6
    return [B64_MAP[data[off + i]] for i in range(6)]


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


def verify_solution(puzzle_number: int, solution_str: str) -> tuple[bool, str | None]:
    """Verify a solution string against a puzzle. Returns (ok, error_msg)."""
    if not isinstance(solution_str, str) or len(solution_str) != 128:
        return False, "solution must be 128 characters"

    # Parse into list of 64 two-char piece IDs
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
    puzzle_cells = decode_puzzle(puzzle_number - 1)

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
    solution = Column(String, nullable=True)  # 128-char board state
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
    solution: Optional[str] = None  # 128-char compact board state
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
def submit_score(body: ScoreSubmitRequest, request: Request):
    """Submit a puzzle solve score."""

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
