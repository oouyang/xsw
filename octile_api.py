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

Solution Encoding (8 chars, compact format)
--------------------------------------------
Encodes the position and orientation of 8 non-grey pieces using mixed-radix
base-92. Grey piece positions are known from puzzle data.

Each piece has a placement index combining top-left position and orientation:
  - Non-square pieces: H placements first (row × cols_avail + col), then V
  - Square pieces: single orientation (row × cols_avail + col)

Piece order and placement counts:
  0: red1   (2×3) — H:42 + V:42 = 84 placements
  1: red2   (1×4) — H:40 + V:40 = 80
  2: white1 (1×5) — H:32 + V:32 = 64
  3: white2 (2×2) — square:      49
  4: blue1  (2×5) — H:28 + V:28 = 56
  5: blue2  (3×4) — H:30 + V:30 = 60
  6: yel1   (3×3) — square:      36
  7: yel2   (2×4) — H:35 + V:35 = 70

H placements: cols_avail = 9 - piece_cols, index = row × cols_avail + col
V placements: offset by hCount, cols_avail = 9 - piece_rows,
              index = hCount + row × cols_avail + col

Combined as mixed-radix big integer (little-endian by piece order):
  n = p0 + N0×(p1 + N1×(p2 + ... ))
  → 8 base-92 chars (little-endian): n%92, (n÷92)%92, ...

Total: 84×80×64×49×56×60×36×70 = 178,437,095,424,000 < 92⁸ = 5.13×10¹⁵ ✓
All intermediate values < 2⁵³ (Number.MAX_SAFE_INTEGER) ✓

Legacy Format (128 chars)
-------------------------
64 × 2-char piece IDs: g1/g2/g3/r1/r2/w1/w2/b1/b2/y1/y2
Still accepted for backward compatibility.
"""

import hashlib
import hmac
import os
import secrets
import time as _time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from passlib.hash import pbkdf2_sha256 as _pw_hasher

from sqlalchemy import (
    create_engine,
    Boolean,
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

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Puzzle data and verification constants
# ---------------------------------------------------------------------------
# Base-92 alphabet: printable ASCII 33-126, excluding ' (39) and \ (92)
P92 = '!"#$%&()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{|}~'
P92_MAP = {c: i for i, c in enumerate(P92)}

# Loaded lazily from puzzle_data.py to keep this file readable
_PUZZLE_DATA: str | None = None
PUZZLE_COUNT = 11378  # base puzzles stored in puzzle data
TOTAL_PUZZLE_COUNT = PUZZLE_COUNT * 8  # 91024 — with D4 symmetry transforms


def _get_puzzle_data() -> str:
    global _PUZZLE_DATA
    if _PUZZLE_DATA is None:
        from octile_puzzle_data import PUZZLE_DATA
        _PUZZLE_DATA = PUZZLE_DATA
    return _PUZZLE_DATA


# Difficulty levels: 1=easy, 2=medium, 3=hard, 4=hell (nightmare in UI)
_DIFFICULTY_DATA: dict | None = None
DIFFICULTY_LABELS = {1: "easy", 2: "medium", 3: "hard", 4: "hell"}

# EXP rewards per difficulty level (aligned with client EXP_BASE)
EXP_BASE = {1: 100, 2: 250, 3: 750, 4: 2000}
# Par times per difficulty (seconds) — aligned with client PAR_TIMES
PAR_TIMES = {1: 60, 2: 90, 3: 120, 4: 180}


def calc_skill_grade(difficulty: int, resolve_time: float) -> str:
    """Calculate skill grade: S (<=par), A (<=2x par), B (normal).

    Note: server cannot know hint usage, so hint-based A grade
    is only applied client-side. Server grades purely on time.
    """
    par = PAR_TIMES.get(difficulty, 90)
    if resolve_time <= par:
        return "S"
    if resolve_time <= par * 2:
        return "A"
    return "B"


def grade_multiplier(grade: str) -> float:
    if grade == "S":
        return 2.0
    if grade == "A":
        return 1.5
    return 1.0


def calc_exp(difficulty: int, resolve_time: float) -> int:
    """Calculate EXP earned for a puzzle solve (server-authoritative).

    EXP_BASE: easy=100, medium=250, hard=750, nightmare=2000
    Grade multiplier: S=×2.0, A=×1.5, B=×1.0
    """
    base = EXP_BASE.get(difficulty, 100)
    grade = calc_skill_grade(difficulty, resolve_time)
    return round(base * grade_multiplier(grade))


# Legacy alias for backward compatibility with old backfill data
def calc_puzzle_coins(difficulty: int, resolve_time: float) -> int:
    """Deprecated — use calc_exp(). Kept for backfill compatibility."""
    return calc_exp(difficulty, resolve_time)


def _get_difficulty_data() -> dict:
    global _DIFFICULTY_DATA
    if _DIFFICULTY_DATA is None:
        import json

        path = os.path.join(os.path.dirname(__file__), "difficulty_levels.json")
        with open(path) as f:
            _DIFFICULTY_DATA = json.load(f)
    return _DIFFICULTY_DATA


def get_puzzle_difficulty(puzzle_number: int) -> int:
    """Get difficulty level (1-4) for a 1-based puzzle number."""
    base, _ = _decompose_puzzle_number(puzzle_number)
    return _get_difficulty_data()["levels"][base]


def get_puzzle_attempts(puzzle_number: int) -> int:
    """Get solver attempt count for a 1-based puzzle number."""
    base, _ = _decompose_puzzle_number(puzzle_number)
    return _get_difficulty_data()["attempts"][base]


# Sorted base puzzle indices per level (sorted by ascending attempts)
_LEVEL_BASES: dict[int, list[int]] | None = None


def _get_level_bases() -> dict[int, list[int]]:
    """Return {level: [base_indices sorted by attempts ascending]}."""
    global _LEVEL_BASES
    if _LEVEL_BASES is not None:
        return _LEVEL_BASES

    data = _get_difficulty_data()
    levels_list = data["levels"]
    attempts_list = data["attempts"]

    by_level: dict[int, list[tuple[int, int]]] = {1: [], 2: [], 3: [], 4: []}
    for base_idx, (level, att) in enumerate(zip(levels_list, attempts_list)):
        by_level[level].append((att, base_idx))

    _LEVEL_BASES = {}
    for level, items in by_level.items():
        items.sort()  # sort by attempts ascending
        _LEVEL_BASES[level] = [base_idx for _, base_idx in items]

    return _LEVEL_BASES


def level_slot_to_puzzle(level: int, slot: int) -> tuple[int, int] | None:
    """Map (level 1-4, slot 1-based) to (puzzle_number, base_index).

    Interleaved ordering — consecutive slots use different base puzzles:
      slot 1:   base1_transform0
      slot 2:   base2_transform0
      ...
      slot N:   baseN_transform0
      slot N+1: base1_transform1
      ...

    Returns (puzzle_number_1based, base_0index) or None if slot out of range.
    """
    bases = _get_level_bases().get(level)
    if bases is None:
        return None

    num_bases = len(bases)
    total = num_bases * 8
    if slot < 1 or slot > total:
        return None

    slot_0 = slot - 1
    base_pos = slot_0 % num_bases
    transform = slot_0 // num_bases
    base_idx = bases[base_pos]
    puzzle_number = transform * PUZZLE_COUNT + base_idx + 1
    return puzzle_number, base_idx


def get_level_total(level: int) -> int:
    """Total puzzles in a level (bases × 8 transforms)."""
    bases = _get_level_bases().get(level)
    return len(bases) * 8 if bases else 0


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


# ---------------------------------------------------------------------------
# D4 symmetry: 8 transforms (4 rotations × 2 mirrors) on 8×8 board
# ---------------------------------------------------------------------------
# Block layout (backward compatible):
#   1..11378     → transform 0 (identity, original puzzles)
#   11379..22756 → transform 1 (rotate 90° CW)
#   22757..34134 → transform 2 (rotate 180°)
#   34135..45512 → transform 3 (rotate 270° CW)
#   45513..56890 → transform 4 (mirror horizontal)
#   56891..68268 → transform 5 (mirror + rotate 90°)
#   68269..79646 → transform 6 (mirror + rotate 180°)
#   79647..91024 → transform 7 (mirror + rotate 270°)


def _transform_cell(cell: int, transform: int) -> int:
    """Apply D4 symmetry transform to a cell index on 8×8 board."""
    r, c = divmod(cell, 8)
    if transform == 1:
        r, c = c, 7 - r
    elif transform == 2:
        r, c = 7 - r, 7 - c
    elif transform == 3:
        r, c = 7 - c, r
    elif transform == 4:
        r, c = r, 7 - c
    elif transform == 5:
        r, c = 7 - c, 7 - r
    elif transform == 6:
        r, c = 7 - r, c
    elif transform == 7:
        r, c = c, r
    return r * 8 + c


def _decompose_puzzle_number(puzzle_number: int) -> tuple[int, int]:
    """Decompose extended puzzle number (1-based) into (base_0_index, transform).

    Returns (base_index, transform) where base_index is 0-based and transform is 0-7.
    """
    idx = puzzle_number - 1
    transform = idx // PUZZLE_COUNT  # 0-7
    base = idx % PUZZLE_COUNT  # 0-based
    return base, transform


def decode_puzzle_extended(puzzle_number: int) -> list[int]:
    """Decode puzzle by 1-based extended number, applying D4 transform.

    For puzzle_number 1–11378, returns the original (identity) puzzle.
    For 11379–91024, returns the base puzzle with rotation/mirror applied.
    """
    base, transform = _decompose_puzzle_number(puzzle_number)
    cells = decode_puzzle(base)
    if transform == 0:
        return cells
    return [_transform_cell(c, transform) for c in cells]


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


# Piece encoding: 8-char base-92 mixed-radix (position+direction per piece)
_PIECE_ENC = [
    {"id": "r1", "r": 2, "c": 3, "sq": False},
    {"id": "r2", "r": 1, "c": 4, "sq": False},
    {"id": "w1", "r": 1, "c": 5, "sq": False},
    {"id": "w2", "r": 2, "c": 2, "sq": True},
    {"id": "b1", "r": 2, "c": 5, "sq": False},
    {"id": "b2", "r": 3, "c": 4, "sq": False},
    {"id": "y1", "r": 3, "c": 3, "sq": True},
    {"id": "y2", "r": 2, "c": 4, "sq": False},
]
for _p in _PIECE_ENC:
    _p["hN"] = (9 - _p["r"]) * (9 - _p["c"])
    _p["N"] = _p["hN"] if _p["sq"] else _p["hN"] * 2


def _decode_compact_solution(solution_str: str) -> list[str] | None:
    """Decode an 8-char base-92 compact solution into a 64-cell board.

    Each of 8 non-grey pieces is encoded as a mixed-radix placement index
    combining position (top-left cell) and orientation (H/V).
    Returns list of 64 piece short-IDs, or None on decode error.
    Non-piece cells are left as None.
    """
    if len(solution_str) != 8:
        return None
    for c in solution_str:
        if c not in P92_MAP:
            return None

    # Decode base-92 → big integer
    n = 0
    for i in range(7, -1, -1):
        n = n * 92 + P92_MAP[solution_str[i]]

    board: list[str | None] = [None] * 64

    for p in _PIECE_ENC:
        pi = n % p["N"]
        n //= p["N"]

        if p["sq"]:
            cols_avail = 9 - p["c"]
            row, col = divmod(pi, cols_avail)
            h, w = p["r"], p["c"]
        elif pi < p["hN"]:
            cols_avail = 9 - p["c"]
            row, col = divmod(pi, cols_avail)
            h, w = p["r"], p["c"]
        else:
            adj = pi - p["hN"]
            cols_avail = 9 - p["r"]
            row, col = divmod(adj, cols_avail)
            h, w = p["c"], p["r"]

        if row + h > 8 or col + w > 8:
            return None

        pid = p["id"]
        for dr in range(h):
            for dc in range(w):
                board[(row + dr) * 8 + (col + dc)] = pid

    return board  # type: ignore[return-value]


def verify_solution(puzzle_number: int, solution_str: str) -> tuple[bool, str | None]:
    """Verify a solution string against a puzzle. Returns (ok, error_msg).

    Accepts two formats:
    - 128-char legacy: 64 × 2-char piece IDs (g1/g2/g3/r1/r2/w1/w2/b1/b2/y1/y2)
    - 8-char compact: base-92 mixed-radix placement encoding
    """
    if not isinstance(solution_str, str) or len(solution_str) not in (8, 128):
        return False, "solution must be 8 or 128 characters"

    puzzle_cells = decode_puzzle_extended(puzzle_number)

    if len(solution_str) == 8:
        # --- Compact format (8-char placement-based) ---
        board = _decode_compact_solution(solution_str)
        if board is None:
            return False, "failed to decode compact solution"

        # Fill in grey cells
        board[puzzle_cells[0]] = "g1"
        board[puzzle_cells[1]] = "g2"
        board[puzzle_cells[2]] = "g2"
        board[puzzle_cells[3]] = "g3"
        board[puzzle_cells[4]] = "g3"
        board[puzzle_cells[5]] = "g3"

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

    # Server-calculated rewards (authoritative, not client-provided)
    coins = Column(Integer, default=0)  # legacy, kept for backward compat
    exp = Column(Integer, default=0)
    diamonds = Column(Integer, default=0)

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


class OctileUser(OctileBase):
    """Octile player account for auth and progress sync."""

    __tablename__ = "octile_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    browser_uuid = Column(String, nullable=True, index=True)
    is_verified = Column(Boolean, default=False)
    otp_code = Column(String, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    last_login_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<OctileUser(id={self.id}, email='{self.email}')>"


# ---------------------------------------------------------------------------
# Auth configuration
# ---------------------------------------------------------------------------
OCTILE_JWT_SECRET = os.getenv("OCTILE_JWT_SECRET", "octile-change-me-in-production")
OCTILE_JWT_EXPIRY_DAYS = 30
_octile_email_sender = None


def _get_email_sender():
    """Lazy-init email sender for Octile OTP emails."""
    global _octile_email_sender
    if _octile_email_sender is not None:
        return _octile_email_sender
    smtp_host = os.getenv("OCTILE_SMTP_HOST", os.getenv("SMTP_HOST", ""))
    smtp_user = os.getenv("OCTILE_SMTP_USER", "")
    if not smtp_host or not smtp_user:
        return None
    from email_sender import EmailSender
    _octile_email_sender = EmailSender(
        smtp_host=smtp_host,
        smtp_port=int(os.getenv("OCTILE_SMTP_PORT", os.getenv("SMTP_PORT", "587"))),
        smtp_user=smtp_user,
        smtp_password=os.getenv("OCTILE_SMTP_PASSWORD", os.getenv("SMTP_PASSWORD", "")),
        from_email=os.getenv("OCTILE_FROM_EMAIL", smtp_user),
        from_name="Octile",
    )
    return _octile_email_sender


def _create_octile_jwt(user_id: int, display_name: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "name": display_name,
        "email": email,
        "iat": now,
        "exp": now + timedelta(days=OCTILE_JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, OCTILE_JWT_SECRET, algorithm="HS256")


def _decode_octile_jwt(token: str) -> dict:
    return jwt.decode(token, OCTILE_JWT_SECRET, algorithms=["HS256"])


_octile_bearer = HTTPBearer(auto_error=False)


async def require_octile_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_octile_bearer),
) -> dict:
    if not credentials:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        return _decode_octile_jwt(credentials.credentials)
    except jwt.ExpiredSignatureError:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# OTP rate limiting: track attempts per email
_otp_attempts: dict[str, list[float]] = defaultdict(list)
OTP_MAX_ATTEMPTS = 5
OTP_WINDOW_SECONDS = 900  # 15 minutes


def _check_otp_rate_limit(email: str) -> bool:
    """Return True if rate-limited."""
    now = _time.time()
    attempts = _otp_attempts[email]
    # Prune old attempts
    _otp_attempts[email] = [t for t in attempts if now - t < OTP_WINDOW_SECONDS]
    if len(_otp_attempts[email]) >= OTP_MAX_ATTEMPTS:
        return True
    _otp_attempts[email].append(now)
    return False


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

    print(f"[Octile] Database initialized: {db_url}")


def _migrate_db():
    """Add new columns to existing tables (safe to run multiple times)."""
    migrations = [
        "ALTER TABLE octile_scores ADD COLUMN solution TEXT",
        "ALTER TABLE octile_scores ADD COLUMN flagged INTEGER DEFAULT 0",
        "ALTER TABLE octile_scores ADD COLUMN coins INTEGER DEFAULT 0",
        "ALTER TABLE octile_scores ADD COLUMN exp INTEGER DEFAULT 0",
        "ALTER TABLE octile_scores ADD COLUMN diamonds INTEGER DEFAULT 0",
    ]
    with _engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(sql_text(sql))
            except Exception:
                pass  # Column already exists

    # Backfill EXP/diamonds for existing scores (idempotent — only updates rows with 0)
    _backfill_rewards()


def _backfill_rewards():
    """Calculate EXP and diamonds for historical scores that have exp=0.

    Runs once at startup. Safe to re-run — only touches rows where exp=0.
    Also backfills coins=0 rows for legacy compatibility.
    Uses batch processing to avoid loading all rows into memory.
    """
    session = _SessionLocal()
    try:
        count = session.query(func.count(OctileScore.id)).filter(
            OctileScore.exp == 0
        ).scalar()
        if count == 0:
            return

        print(f"[Octile] Backfilling EXP/diamonds for {count} historical scores...")
        batch_size = 500
        updated = 0
        while True:
            rows = (
                session.query(OctileScore)
                .filter(OctileScore.exp == 0)
                .limit(batch_size)
                .all()
            )
            if not rows:
                break
            for score in rows:
                try:
                    difficulty = get_puzzle_difficulty(score.puzzle_number)
                    exp = calc_exp(difficulty, score.resolve_time)
                    if score.flagged:
                        exp = 0
                    score.exp = exp
                    score.diamonds = 0 if score.flagged else 1
                    # Also backfill coins if still 0
                    if not score.coins:
                        score.coins = exp  # align legacy coins with EXP
                except Exception:
                    score.exp = 0
                    score.diamonds = 0
                    if not score.coins:
                        score.coins = 0
            session.commit()
            updated += len(rows)

        print(f"[Octile] Backfill complete: {updated} scores updated with EXP/diamonds")
    except Exception as e:
        session.rollback()
        print(f"[Octile] Backfill failed: {e}")
    finally:
        session.close()


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
    coins: int = 0  # legacy, kept for backward compat
    exp: int = 0
    diamonds: int = 0
    grade: str = "B"


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
    try:
        difficulty = get_puzzle_difficulty(score.puzzle_number)
        grade = calc_skill_grade(difficulty, score.resolve_time)
    except Exception:
        grade = "B"
    return ScoreResponse(
        id=score.id,
        puzzle_number=score.puzzle_number,
        resolve_time=score.resolve_time,
        browser_uuid=score.browser_uuid,
        created_at=created,
        timestamp_utc=created,  # legacy alias so old clients can sort by this
        flagged=score.flagged or 0,
        coins=score.coins or 0,
        exp=score.exp or 0,
        diamonds=score.diamonds or 0,
        grade=grade,
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
    if not (1 <= body.puzzle_number <= TOTAL_PUZZLE_COUNT):
        return JSONResponse(
            status_code=400,
            content={"detail": f"puzzle_number must be 1–{TOTAL_PUZZLE_COUNT}"},
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

        # Server-authoritative reward calculation
        difficulty = get_puzzle_difficulty(body.puzzle_number)
        exp = calc_exp(difficulty, body.resolve_time)
        diamonds = 1  # 1 diamond per puzzle solved
        if flagged:
            exp = 0
            diamonds = 0

        score = OctileScore(
            puzzle_number=body.puzzle_number,
            resolve_time=body.resolve_time,
            browser_uuid=body.browser_uuid,
            timestamp_utc=timestamp,
            os=body.os,
            browser=body.browser,
            solution=body.solution,
            flagged=flagged,
            coins=exp,  # legacy coins = exp for backward compat
            exp=exp,
            diamonds=diamonds,
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


@octile_router.get("/leaderboard")
def get_leaderboard(limit: int = 50):
    """EXP-based leaderboard. Returns players ranked by total server-verified EXP.

    Only counts non-flagged scores. This is the authoritative ranking
    since EXP is calculated server-side from difficulty + solve time.
    """
    limit = min(max(limit, 1), 200)
    session = get_session()
    try:
        rows = (
            session.query(
                OctileScore.browser_uuid,
                func.sum(OctileScore.exp).label("total_exp"),
                func.sum(OctileScore.diamonds).label("total_diamonds"),
                func.count(func.distinct(OctileScore.puzzle_number)).label("puzzles"),
                func.avg(OctileScore.resolve_time).label("avg_time"),
            )
            .filter(OctileScore.flagged == 0)
            .group_by(OctileScore.browser_uuid)
            .order_by(func.sum(OctileScore.exp).desc())
            .limit(limit)
            .all()
        )
        return {
            "total_players": len(rows),
            "leaderboard": [
                {
                    "browser_uuid": r.browser_uuid,
                    "total_exp": r.total_exp or 0,
                    "total_diamonds": r.total_diamonds or 0,
                    "total_coins": r.total_exp or 0,  # legacy alias
                    "puzzles": r.puzzles,
                    "avg_time": round(r.avg_time, 1) if r.avg_time else 0,
                }
                for r in rows
            ],
        }
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


@octile_router.get("/puzzle/{number}")
def get_puzzle(number: int):
    """Get decoded puzzle cells by extended puzzle number (1-based, up to 91024)."""
    if not (1 <= number <= TOTAL_PUZZLE_COUNT):
        return JSONResponse(
            status_code=400,
            content={"detail": f"puzzle_number must be 1–{TOTAL_PUZZLE_COUNT}"},
        )
    base, transform = _decompose_puzzle_number(number)
    cells = decode_puzzle_extended(number)
    level = get_puzzle_difficulty(number)
    return {
        "puzzle_number": number,
        "base_puzzle": base + 1,
        "transform": transform,
        "cells": cells,
        "difficulty": level,
        "difficulty_label": DIFFICULTY_LABELS[level],
    }


@octile_router.get("/levels")
def get_levels():
    """Return puzzle counts per difficulty level."""
    return {
        level_name: get_level_total(level_num)
        for level_num, level_name in DIFFICULTY_LABELS.items()
    }


@octile_router.get("/level/{level}/puzzle/{slot}")
def get_level_puzzle(level: str, slot: int):
    """Get puzzle by difficulty level and slot (1-based, sequential by difficulty).

    Level: easy, medium, hard, hell
    Slot: 1 to level_total (8 transforms per base, ordered easiest first)
    """
    level_num = next((k for k, v in DIFFICULTY_LABELS.items() if v == level), None)
    if level_num is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "level must be easy, medium, hard, or hell"},
        )

    total = get_level_total(level_num)
    if slot < 1 or slot > total:
        return JSONResponse(
            status_code=400,
            content={"detail": f"slot must be 1–{total}"},
        )

    result = level_slot_to_puzzle(level_num, slot)
    if result is None:
        return JSONResponse(status_code=400, content={"detail": "invalid slot"})

    puzzle_number, base_idx = result
    cells = decode_puzzle_extended(puzzle_number)
    return {
        "puzzle_number": puzzle_number,
        "level": level,
        "slot": slot,
        "total": total,
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str
    browser_uuid: Optional[str] = None


class VerifyRequest(BaseModel):
    email: str
    otp_code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    otp_code: str
    new_password: str


def _send_otp_email(email: str, otp: str, purpose: str = "verify") -> bool:
    sender = _get_email_sender()
    if not sender:
        print(f"[Octile Auth] Email not configured, OTP for {email}: {otp}")
        return True  # Don't block registration in dev
    subject = "Octile verification code" if purpose == "verify" else "Octile password reset"
    body = (
        f"<div style='font-family:sans-serif;max-width:400px;margin:0 auto;padding:20px'>"
        f"<h2 style='color:#1a1a2e'>Octile</h2>"
        f"<p>Your verification code is:</p>"
        f"<div style='font-size:32px;font-weight:bold;letter-spacing:8px;"
        f"color:#2ecc71;padding:16px;text-align:center'>{otp}</div>"
        f"<p style='color:#888;font-size:13px'>This code expires in 10 minutes.</p>"
        f"</div>"
    )
    result = sender.send_email(email, subject, body, is_html=True)
    return result.get("status") == "success"


@octile_router.post("/auth/register")
def auth_register(req: RegisterRequest):
    """Register a new account. Sends OTP to email for verification."""
    email = req.email.strip().lower()
    if not email or "@" not in email or len(req.password) < 6:
        return JSONResponse(status_code=400, content={"detail": "Invalid email or password (min 6 chars)"})

    if _check_otp_rate_limit(email):
        return JSONResponse(status_code=429, content={"detail": "Too many attempts, try again later"})

    session = get_session()
    try:
        existing = session.query(OctileUser).filter(OctileUser.email == email).first()
        if existing and existing.is_verified:
            return JSONResponse(status_code=409, content={"detail": "Email already registered"})

        otp = f"{secrets.randbelow(1000000):06d}"
        otp_expires = datetime.utcnow() + timedelta(minutes=10)
        pw_hash = _pw_hasher.hash(req.password)

        if existing and not existing.is_verified:
            # Re-register: update pending account
            existing.password_hash = pw_hash
            existing.display_name = req.display_name.strip() or email.split("@")[0]
            existing.browser_uuid = req.browser_uuid
            existing.otp_code = otp
            existing.otp_expires_at = otp_expires
        else:
            user = OctileUser(
                email=email,
                password_hash=pw_hash,
                display_name=req.display_name.strip() or email.split("@")[0],
                browser_uuid=req.browser_uuid,
                otp_code=otp,
                otp_expires_at=otp_expires,
            )
            session.add(user)

        session.commit()
        _send_otp_email(email, otp, purpose="verify")
        return {"status": "pending", "message": "Verification code sent to your email"}
    finally:
        session.close()


@octile_router.post("/auth/verify")
def auth_verify(req: VerifyRequest):
    """Verify email with OTP code. Returns JWT on success."""
    email = req.email.strip().lower()
    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user:
            return JSONResponse(status_code=404, content={"detail": "Account not found"})
        if user.is_verified:
            return JSONResponse(status_code=400, content={"detail": "Already verified, please login"})
        if not user.otp_code or user.otp_code != req.otp_code.strip():
            return JSONResponse(status_code=400, content={"detail": "Invalid verification code"})
        if user.otp_expires_at and user.otp_expires_at < datetime.utcnow():
            return JSONResponse(status_code=400, content={"detail": "Code expired, please register again"})

        user.is_verified = True
        user.otp_code = None
        user.otp_expires_at = None
        user.last_login_at = datetime.now(timezone.utc)
        session.commit()

        token = _create_octile_jwt(user.id, user.display_name, user.email)
        return {
            "access_token": token,
            "user": {"id": user.id, "display_name": user.display_name, "email": user.email},
        }
    finally:
        session.close()


@octile_router.post("/auth/login")
def auth_login(req: LoginRequest):
    """Login with email and password. Returns JWT."""
    email = req.email.strip().lower()
    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user or not user.is_verified:
            return JSONResponse(status_code=401, content={"detail": "Invalid email or password"})
        if not _pw_hasher.verify(req.password, user.password_hash):
            return JSONResponse(status_code=401, content={"detail": "Invalid email or password"})

        user.last_login_at = datetime.now(timezone.utc)
        session.commit()

        token = _create_octile_jwt(user.id, user.display_name, user.email)
        return {
            "access_token": token,
            "user": {"id": user.id, "display_name": user.display_name, "email": user.email},
        }
    finally:
        session.close()


@octile_router.post("/auth/forgot-password")
def auth_forgot_password(req: ForgotPasswordRequest):
    """Send a password reset OTP to the email."""
    email = req.email.strip().lower()

    if _check_otp_rate_limit(email):
        return JSONResponse(status_code=429, content={"detail": "Too many attempts, try again later"})

    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user or not user.is_verified:
            # Don't reveal whether email exists
            return {"status": "sent", "message": "If the email is registered, a reset code was sent"}

        otp = f"{secrets.randbelow(1000000):06d}"
        user.otp_code = otp
        user.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        session.commit()

        _send_otp_email(email, otp, purpose="reset")
        return {"status": "sent", "message": "If the email is registered, a reset code was sent"}
    finally:
        session.close()


@octile_router.post("/auth/reset-password")
def auth_reset_password(req: ResetPasswordRequest):
    """Reset password with OTP code."""
    email = req.email.strip().lower()
    if len(req.new_password) < 6:
        return JSONResponse(status_code=400, content={"detail": "Password must be at least 6 characters"})

    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user or not user.is_verified:
            return JSONResponse(status_code=404, content={"detail": "Account not found"})
        if not user.otp_code or user.otp_code != req.otp_code.strip():
            return JSONResponse(status_code=400, content={"detail": "Invalid reset code"})
        if user.otp_expires_at and user.otp_expires_at < datetime.utcnow():
            return JSONResponse(status_code=400, content={"detail": "Code expired, request a new one"})

        user.password_hash = _pw_hasher.hash(req.new_password)
        user.otp_code = None
        user.otp_expires_at = None
        session.commit()

        return {"status": "ok", "message": "Password reset successfully"}
    finally:
        session.close()


@octile_router.get("/auth/me")
def auth_me(user: dict = Depends(require_octile_auth)):
    """Get current authenticated user info."""
    return {
        "id": int(user["sub"]),
        "display_name": user["name"],
        "email": user["email"],
    }
