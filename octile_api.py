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
import re as _re
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
    Text,
    DateTime,
    Index,
    and_,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import text as sql_text

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
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


# ---------------------------------------------------------------------------
# ELO Rating System
# ---------------------------------------------------------------------------
ELO_INITIAL = 1200
# Puzzle ELO based on difficulty (midpoint of designed ranges)
PUZZLE_ELO = {1: 800, 2: 1250, 3: 1850, 4: 2600}
# Grade to performance score
GRADE_SCORE = {"S": 1.0, "A": 0.7, "B": 0.4}


def calc_elo_change(
    player_elo: float, puzzle_difficulty: int, grade: str, solves_count: int
) -> float:
    """Calculate ELO change for a single solve.

    K-factor decays with experience:
      - First 30 solves: K=40 (volatile, fast calibration)
      - 30-100 solves: K=20
      - 100+ solves: K=10 (stable)
    """
    puzzle_elo = PUZZLE_ELO.get(puzzle_difficulty, 1250)
    actual = GRADE_SCORE.get(grade, 0.4)

    # Expected performance based on ELO gap
    expected = 1.0 / (1.0 + 10.0 ** ((puzzle_elo - player_elo) / 400.0))

    # K-factor
    if solves_count < 30:
        k = 40
    elif solves_count < 100:
        k = 20
    else:
        k = 10

    return k * (actual - expected)


def calc_elo_for_player(session, browser_uuid: str) -> float:
    """Recalculate ELO from scratch by replaying all scores in order."""
    scores = (
        session.query(
            OctileScore.puzzle_number, OctileScore.resolve_time, OctileScore.flagged
        )
        .filter(OctileScore.browser_uuid == browser_uuid)
        .order_by(OctileScore.created_at.asc())
        .all()
    )
    elo = float(ELO_INITIAL)
    for i, (puzzle_num, resolve_time, flagged) in enumerate(scores):
        if flagged:
            continue
        try:
            difficulty = get_puzzle_difficulty(puzzle_num)
        except Exception:
            continue
        grade = calc_skill_grade(difficulty, resolve_time)
        elo += calc_elo_change(elo, difficulty, grade, i)
    return round(elo, 1)


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

    # Authenticated user link (nullable for anonymous scores)
    user_id = Column(Integer, nullable=True, index=True)

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    __table_args__ = (
        Index("idx_octile_puzzle_time", "puzzle_number", "resolve_time"),
        Index("idx_octile_uuid_puzzle", "browser_uuid", "puzzle_number"),
        Index("idx_octile_uuid_created", "browser_uuid", "created_at"),
        Index("idx_octile_uuid_userid", "browser_uuid", "user_id"),
        Index("idx_octile_userid_created", "user_id", "created_at"),
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
    picture = Column(String, nullable=True)
    browser_uuid = Column(String, nullable=True, index=True)
    is_verified = Column(Boolean, default=False)
    otp_code = Column(String, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<OctileUser(id={self.id}, email='{self.email}')>"


class OctileProgress(OctileBase):
    """Server-side progress for authenticated players."""

    __tablename__ = "octile_progress"

    user_id = Column(Integer, primary_key=True)
    browser_uuid = Column(String, nullable=True, index=True)
    level_easy = Column(Integer, default=0)
    level_medium = Column(Integer, default=0)
    level_hard = Column(Integer, default=0)
    level_hell = Column(Integer, default=0)
    exp = Column(Integer, default=0)
    diamonds = Column(Integer, default=0)
    chapters_completed = Column(Integer, default=0)
    achievements = Column(Text, default="[]")
    streak_count = Column(Integer, default=0)
    streak_last_date = Column(String, nullable=True)
    months = Column(Text, default="[]")
    total_solved = Column(Integer, default=0)
    total_time = Column(Float, default=0)
    grades_s = Column(Integer, default=0)
    grades_a = Column(Integer, default=0)
    grades_b = Column(Integer, default=0)
    daily_tasks_date = Column(String, nullable=True)
    daily_tasks_claimed = Column(Text, default="[]")
    daily_tasks_bonus_claimed = Column(Integer, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Team League models
# ---------------------------------------------------------------------------

LEAGUE_TIERS = {
    0: {"name_en": "Bronze", "name_zh": "青銅", "team_size": 10, "color": "#cd7f32"},
    1: {"name_en": "Silver", "name_zh": "白銀", "team_size": 8, "color": "#c0c0c0"},
    2: {"name_en": "Gold", "name_zh": "黃金", "team_size": 7, "color": "#ffd700"},
    3: {"name_en": "Sapphire", "name_zh": "藍寶石", "team_size": 5, "color": "#0f52ba"},
    4: {"name_en": "Ruby", "name_zh": "紅寶石", "team_size": 5, "color": "#e0115f"},
    5: {"name_en": "Emerald", "name_zh": "祖母綠", "team_size": 5, "color": "#50c878"},
    6: {"name_en": "Amethyst", "name_zh": "紫水晶", "team_size": 5, "color": "#9966cc"},
    7: {"name_en": "Obsidian", "name_zh": "黑曜石", "team_size": 5, "color": "#1c1c1c"},
}
LEAGUE_PROMO_DAYS = 3
LEAGUE_DEMOTE_DAYS = 3
LEAGUE_PROMO_TOP_N = 2  # safety zone: top 2 for promotion
LEAGUE_MIN_ACTIVE_FOR_EVAL = 3  # need >= 3 active members to evaluate
LEAGUE_MIN_EXP_FOR_PROMO = 500  # must earn >= 500 EXP/day to count for promotion
LEAGUE_DAILY_EXP_CAP = 20000  # anti-cheat: max daily EXP before flagging


class LeagueMember(OctileBase):
    __tablename__ = "league_members"
    user_id = Column(Integer, primary_key=True)
    tier = Column(Integer, default=0, nullable=False)
    team_id = Column(Integer, nullable=True, index=True)
    today_exp = Column(Integer, default=0)
    promo_streak = Column(Integer, default=0)
    demote_streak = Column(Integer, default=0)
    inactive_days = Column(Integer, default=0)
    last_eval_date = Column(String, nullable=True)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        Index("idx_league_member_team_exp", "team_id", "today_exp"),
        Index("idx_league_member_tier", "tier"),
    )


class LeagueTeam(OctileBase):
    __tablename__ = "league_teams"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tier = Column(Integer, nullable=False, index=True)
    month = Column(String, nullable=False, index=True)
    team_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LeagueDailyExp(OctileBase):
    __tablename__ = "league_daily_exp"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    team_id = Column(Integer, nullable=False, index=True)
    date = Column(String, nullable=False)
    exp = Column(Integer, default=0)
    __table_args__ = (
        Index("idx_league_daily_user_date", "user_id", "date", unique=True),
        Index("idx_league_daily_team_date", "team_id", "date"),
    )


class LeagueHistory(OctileBase):
    __tablename__ = "league_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    event = Column(String, nullable=False)
    from_tier = Column(Integer, nullable=True)
    to_tier = Column(Integer, nullable=True)
    date = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Auth configuration
# ---------------------------------------------------------------------------
OCTILE_JWT_SECRET = os.getenv("OCTILE_JWT_SECRET", "octile-change-me-in-production")
OCTILE_JWT_EXPIRY_DAYS = 365

# Google OAuth (server-side redirect flow)
OCTILE_GOOGLE_CLIENT_ID = os.getenv(
    "OCTILE_GOOGLE_CLIENT_ID", os.getenv("GOOGLE_CLIENT_ID", "")
)
OCTILE_GOOGLE_CLIENT_SECRET = os.getenv("OCTILE_GOOGLE_CLIENT_SECRET", "")
OCTILE_GOOGLE_REDIRECT_URI = os.getenv("OCTILE_GOOGLE_REDIRECT_URI", "")
OCTILE_WORKER_URL = os.getenv(
    "OCTILE_WORKER_URL", "https://octile.owen-ouyang.workers.dev"
)
# Where to send the user after successful Google login
# Android: octile://auth?token=...&name=...
# Web: https://mtaleon.github.io/octile/?auth_token=...&auth_name=...
OCTILE_SITE_URL = os.getenv("OCTILE_SITE_URL", "https://mtaleon.github.io/octile/")

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


def _get_optional_user_id(request: Request) -> Optional[int]:
    """Extract user_id from Authorization header if present. Returns None if anonymous."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = _decode_octile_jwt(auth[7:])
        return int(payload["sub"])
    except Exception:
        return None


_octile_bearer = HTTPBearer(auto_error=False)


async def require_octile_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_octile_bearer),
) -> dict:
    if not credentials:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token"
        )
    try:
        return _decode_octile_jwt(credentials.credentials)
    except jwt.ExpiredSignatureError:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt.InvalidTokenError as e:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def _normalize_email(email: str) -> str:
    """Normalize email to prevent duplicates from aliases/variants.
    - Lowercase
    - Gmail: remove dots, strip +suffix, googlemail.com → gmail.com
    """
    email = email.strip().lower()
    local, _, domain = email.partition("@")
    if not domain:
        return email
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0]  # strip +suffix
        local = local.replace(".", "")  # remove dots
        domain = "gmail.com"  # normalize googlemail
    return local + "@" + domain


def _backfill_scores_for_user(session, user_id: int, browser_uuid: str):
    """Link anonymous scores (user_id=NULL) to the authenticated user by browser_uuid.

    Device takeover protection: skip if another user already claimed scores
    on this browser_uuid (shared device scenario).
    """
    if not browser_uuid:
        return
    # Check if any other user already has scores on this browser_uuid
    other_user = (
        session.query(OctileScore.user_id)
        .filter(
            OctileScore.browser_uuid == browser_uuid,
            OctileScore.user_id.isnot(None),
            OctileScore.user_id != user_id,
        )
        .first()
    )
    if other_user:
        # Another user claimed this device — don't steal their scores
        return
    session.query(OctileScore).filter(
        OctileScore.browser_uuid == browser_uuid,
        OctileScore.user_id.is_(None),
    ).update({"user_id": user_id})
    session.commit()


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
        db_path = os.getenv("OCTILE_DB_PATH", "data/octile.db")
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
        count = (
            session.query(func.count(OctileScore.id))
            .filter(OctileScore.exp == 0)
            .scalar()
        )
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
    elo: Optional[float] = None
    display_name: Optional[str] = None
    picture: Optional[str] = None


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

        # Link to authenticated user if JWT present
        auth_user_id = _get_optional_user_id(request)

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
            user_id=auth_user_id,
            **client_info,
        )
        session.add(score)
        session.commit()
        session.refresh(score)

        # Atomic league EXP update
        if auth_user_id and not flagged and exp > 0:
            session.query(LeagueMember).filter(
                LeagueMember.user_id == auth_user_id
            ).update({LeagueMember.today_exp: LeagueMember.today_exp + exp})
            session.commit()

        # Calculate updated ELO for this player
        resp = _score_to_response(score)
        if not flagged:
            resp.elo = calc_elo_for_player(session, body.browser_uuid)

        return JSONResponse(
            status_code=201,
            content=resp.model_dump(),
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

        # Look up display names via user_id (multi-device) or browser_uuid (legacy)
        resp_scores = [_score_to_response(s) for s in scores]
        # Collect user_ids and browser_uuids from scores
        score_user_ids = list({s.user_id for s in scores if s.user_id})
        score_uuids = list({s.browser_uuid for s in scores})
        user_by_id = {}
        user_by_uuid = {}
        if score_user_ids:
            users = (
                session.query(OctileUser)
                .filter(OctileUser.id.in_(score_user_ids))
                .all()
            )
            user_by_id = {u.id: u for u in users}
        if score_uuids:
            users = (
                session.query(OctileUser)
                .filter(OctileUser.browser_uuid.in_(score_uuids))
                .all()
            )
            user_by_uuid = {u.browser_uuid: u for u in users}
        for s, raw_score in zip(resp_scores, scores):
            u = (
                user_by_id.get(raw_score.user_id)
                if raw_score.user_id
                else user_by_uuid.get(s.browser_uuid)
            )
            if u:
                s.display_name = u.display_name
                s.picture = u.picture

        return ScoreboardResponse(
            puzzle_number=puzzle,
            total=total,
            scores=resp_scores,
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
        # Build a mapping from registered user -> all their browser_uuids
        # so we can attribute ALL scores (including un-backfilled ones) to the user
        all_users = session.query(OctileUser).all()
        user_by_id = {u.id: u for u in all_users}

        # Map: browser_uuid -> user_id (from user table + scores with user_id)
        uuid_to_user_id: dict = {}
        for u in all_users:
            if u.browser_uuid:
                uuid_to_user_id[u.browser_uuid] = u.id

        # Also map from scores that have user_id set
        linked_scores = (
            session.query(OctileScore.browser_uuid, OctileScore.user_id)
            .filter(OctileScore.user_id.isnot(None))
            .distinct()
            .all()
        )
        for row in linked_scores:
            if row.browser_uuid:
                uuid_to_user_id[row.browser_uuid] = row.user_id

        # Single query: all non-flagged scores grouped by browser_uuid
        all_rows = (
            session.query(
                OctileScore.browser_uuid,
                func.sum(OctileScore.exp).label("total_exp"),
                func.sum(OctileScore.diamonds).label("total_diamonds"),
                func.count(func.distinct(OctileScore.puzzle_number)).label("puzzles"),
                func.avg(OctileScore.resolve_time).label("avg_time"),
            )
            .filter(OctileScore.flagged == 0)
            .group_by(OctileScore.browser_uuid)
            .all()
        )

        # Merge rows: authenticated users may have multiple browser_uuids
        user_agg: dict = {}  # user_id -> aggregated stats
        anon_entries = []

        for r in all_rows:
            uid = uuid_to_user_id.get(r.browser_uuid)
            if uid:
                if uid not in user_agg:
                    user_agg[uid] = {
                        "total_exp": 0,
                        "total_diamonds": 0,
                        "puzzles": 0,
                        "avg_time_sum": 0,
                        "avg_time_cnt": 0,
                        "browser_uuid": r.browser_uuid,
                    }
                agg = user_agg[uid]
                agg["total_exp"] += r.total_exp or 0
                agg["total_diamonds"] += r.total_diamonds or 0
                agg["puzzles"] += r.puzzles or 0
                agg["avg_time_sum"] += (r.avg_time or 0) * (r.puzzles or 0)
                agg["avg_time_cnt"] += r.puzzles or 0
            else:
                anon_entries.append(
                    {
                        "browser_uuid": r.browser_uuid,
                        "total_exp": r.total_exp or 0,
                        "total_diamonds": r.total_diamonds or 0,
                        "total_coins": r.total_exp or 0,
                        "puzzles": r.puzzles,
                        "avg_time": round(r.avg_time, 1) if r.avg_time else 0,
                        "display_name": None,
                        "picture": None,
                    }
                )

        # Build authenticated entries
        entries = []
        for uid, agg in user_agg.items():
            u = user_by_id.get(uid)
            avg_t = (
                round(agg["avg_time_sum"] / agg["avg_time_cnt"], 1)
                if agg["avg_time_cnt"]
                else 0
            )
            entries.append(
                {
                    "browser_uuid": agg["browser_uuid"],
                    "total_exp": agg["total_exp"],
                    "total_diamonds": agg["total_diamonds"],
                    "total_coins": agg["total_exp"],
                    "puzzles": agg["puzzles"],
                    "avg_time": avg_t,
                    "display_name": u.display_name if u else None,
                    "picture": u.picture if u else None,
                }
            )

        entries.extend(anon_entries)

        # Sort by total_exp descending, limit
        entries.sort(key=lambda e: e["total_exp"], reverse=True)
        entries = entries[:limit]

        return {
            "total_players": len(entries),
            "leaderboard": entries,
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
def get_levels(transforms: int = 8):
    """Return puzzle counts per difficulty level.

    transforms: number of D4 transforms per base puzzle (1=base only, 8=full set).
    """
    t = max(1, min(8, transforms))
    return {
        level_name: len(_get_level_bases().get(level_num, [])) * t
        for level_num, level_name in DIFFICULTY_LABELS.items()
    }


@octile_router.get("/level/{level}/puzzle/{slot}")
def get_level_puzzle(level: str, slot: int, transforms: int = 8):
    """Get puzzle by difficulty level and slot (1-based, sequential by difficulty).

    Level: easy, medium, hard, hell
    Slot: 1 to level_total
    transforms: 1=base puzzles only, 8=full set with D4 transforms (default)
    """
    level_num = next((k for k, v in DIFFICULTY_LABELS.items() if v == level), None)
    if level_num is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "level must be easy, medium, hard, or hell"},
        )

    t = max(1, min(8, transforms))
    bases = _get_level_bases().get(level_num, [])
    num_bases = len(bases)
    total = num_bases * t

    if slot < 1 or slot > total:
        return JSONResponse(
            status_code=400,
            content={"detail": f"slot must be 1–{total}"},
        )

    # Interleaved ordering: slot → (base_pos, transform)
    slot_0 = slot - 1
    base_pos = slot_0 % num_bases
    transform = slot_0 // num_bases
    base_idx = bases[base_pos]
    puzzle_number = transform * PUZZLE_COUNT + base_idx + 1
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
    browser_uuid: Optional[str] = None


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
    subject = (
        "Octile verification code" if purpose == "verify" else "Octile password reset"
    )
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


class MagicLinkRequest(BaseModel):
    email: str
    browser_uuid: Optional[str] = None


@octile_router.post("/auth/magic-link")
def auth_magic_link(req: MagicLinkRequest):
    """Send a magic sign-in link to the given email."""
    email = _normalize_email(req.email.strip().lower())
    if not email or "@" not in email:
        return JSONResponse({"detail": "Invalid email"}, status_code=400)

    session = get_session()
    try:
        # Find or create user
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user:
            # Auto-create account
            user = OctileUser(
                email=email,
                display_name=email.split("@")[0],
                browser_uuid=req.browser_uuid,
                is_verified=False,
            )
            session.add(user)
            session.flush()

        # Generate a short-lived token (15 min)
        token = secrets.token_urlsafe(32)
        user.otp_code = "magic:" + token
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        if req.browser_uuid and not user.browser_uuid:
            user.browser_uuid = req.browser_uuid
        session.commit()

        # Build magic link URL
        verify_url = (
            OCTILE_WORKER_URL.rstrip("/")
            + "/auth/magic-link/verify?token="
            + token
            + "&uid="
            + str(user.id)
        )

        # Send email
        sender = _get_email_sender()
        if not sender:
            return JSONResponse(
                {"detail": "Email service unavailable"}, status_code=503
            )
        body = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px">
          <h2 style="color:#f1c40f">Octile Sign In</h2>
          <p>Click the button below to sign in to Octile:</p>
          <a href="{verify_url}" style="display:inline-block;padding:14px 28px;background:#2ecc71;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;font-size:16px">Sign In to Octile</a>
          <p style="color:#888;font-size:12px;margin-top:20px">This link expires in 15 minutes. If you didn't request this, ignore this email.</p>
        </div>
        """
        result = sender.send_email(email, "Octile Sign-In Link", body, is_html=True)
        if result.get("status") != "success":
            return JSONResponse({"detail": "Failed to send email"}, status_code=500)

        return {"status": "ok"}
    finally:
        session.close()


@octile_router.get("/auth/magic-link/verify")
def auth_magic_link_verify(token: str, uid: int):
    """Verify magic link token and return JWT. Redirects to app with token."""
    session = get_session()
    try:
        _err_style = 'style="background:#1a1a2e;color:#eee;font-family:sans-serif;text-align:center;padding:60px"'
        _err_btn = f'<a href="{OCTILE_SITE_URL}" style="display:inline-block;margin-top:20px;padding:12px 28px;background:#2ecc71;color:#fff;text-decoration:none;border-radius:8px;font-weight:700">Open Octile</a>'
        user = session.query(OctileUser).filter(OctileUser.id == uid).first()
        if not user or user.otp_code != "magic:" + token:
            return HTMLResponse(
                f'<body {_err_style}><h2 style="color:#e74c3c">Link Invalid</h2>'
                f"<p>This sign-in link is no longer valid.<br>It may have already been used.</p>"
                f"<p>Please open Octile and request a new sign-in link.</p>{_err_btn}</body>",
                status_code=400,
            )
        if user.otp_expires_at and user.otp_expires_at < datetime.now(timezone.utc):
            return HTMLResponse(
                f'<body {_err_style}><h2 style="color:#f39c12">Link Expired</h2>'
                f"<p>This sign-in link has expired (15 minutes).</p>"
                f"<p>Please open Octile and request a new sign-in link.</p>{_err_btn}</body>",
                status_code=400,
            )

        # Mark verified, clear OTP
        user.is_verified = True
        user.otp_code = None
        user.otp_expires_at = None
        user.last_login_at = datetime.now(timezone.utc)
        session.commit()

        # Backfill scores
        _backfill_scores_for_user(session, user)

        # Generate JWT
        jwt_token = _create_octile_jwt(user.id, user.display_name or "", user.email)

        # Redirect to app with token (works for both web and Android deep link)
        safe_name = (user.display_name or "").replace("'", "\\'")
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
        <title>Signing in...</title>
        <script>
        try {{
          if (window.opener) {{
            window.opener.postMessage({{type:'octile-auth',token:'{jwt_token}',name:'{safe_name}'}}, '*');
            window.close();
          }} else {{
            window.location.href = 'octile://auth?token={jwt_token}&name={safe_name}';
            setTimeout(function() {{
              window.location.href = '{OCTILE_SITE_URL}?auth_token={jwt_token}';
            }}, 1000);
          }}
        }} catch(e) {{
          window.location.href = '{OCTILE_SITE_URL}?auth_token={jwt_token}';
        }}
        </script>
        </head><body style="background:#1a1a2e;color:#eee;font-family:sans-serif;text-align:center;padding:60px">
        <h2 style="color:#2ecc71">✓ Signed in!</h2>
        <p>Redirecting to Octile...</p>
        </body></html>"""
        return HTMLResponse(html)
    finally:
        session.close()


@octile_router.post("/auth/register")
def auth_register(req: RegisterRequest):
    """Register a new account. Sends OTP to email for verification."""
    email = _normalize_email(req.email)
    if not email or "@" not in email or len(req.password) < 6:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid email or password (min 6 chars)"},
        )

    if _check_otp_rate_limit(email):
        return JSONResponse(
            status_code=429, content={"detail": "Too many attempts, try again later"}
        )

    session = get_session()
    try:
        existing = session.query(OctileUser).filter(OctileUser.email == email).first()
        if existing and existing.is_verified:
            # Check if this was a Google-created account (has picture or random password)
            if existing.picture:
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "This email is linked to a Google account. Please use Google Sign-In, or login with Google first then set a password."
                    },
                )
            return JSONResponse(
                status_code=409, content={"detail": "Email already registered"}
            )

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
    email = _normalize_email(req.email)
    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user:
            return JSONResponse(
                status_code=404, content={"detail": "Account not found"}
            )
        if user.is_verified:
            return JSONResponse(
                status_code=400, content={"detail": "Already verified, please login"}
            )
        if not user.otp_code or user.otp_code != req.otp_code.strip():
            return JSONResponse(
                status_code=400, content={"detail": "Invalid verification code"}
            )
        if user.otp_expires_at and user.otp_expires_at < datetime.utcnow():
            return JSONResponse(
                status_code=400,
                content={"detail": "Code expired, please register again"},
            )

        user.is_verified = True
        user.otp_code = None
        user.otp_expires_at = None
        user.last_login_at = datetime.now(timezone.utc)
        session.commit()

        _backfill_scores_for_user(session, user.id, user.browser_uuid)

        token = _create_octile_jwt(user.id, user.display_name, user.email)
        return {
            "access_token": token,
            "user": {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
            },
        }
    finally:
        session.close()


@octile_router.post("/auth/login")
def auth_login(req: LoginRequest):
    """Login with email and password. Returns JWT."""
    email = _normalize_email(req.email)
    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user or not user.is_verified:
            return JSONResponse(
                status_code=401, content={"detail": "Invalid email or password"}
            )
        if not _pw_hasher.verify(req.password, user.password_hash):
            return JSONResponse(
                status_code=401, content={"detail": "Invalid email or password"}
            )

        # Link browser_uuid if not already set
        browser_uuid = (req.browser_uuid or "").strip()
        if browser_uuid and not user.browser_uuid:
            user.browser_uuid = browser_uuid

        user.last_login_at = datetime.now(timezone.utc)
        session.commit()

        # Backfill anonymous scores from this device AND the stored device
        _backfill_scores_for_user(session, user.id, browser_uuid)
        if user.browser_uuid and user.browser_uuid != browser_uuid:
            _backfill_scores_for_user(session, user.id, user.browser_uuid)

        token = _create_octile_jwt(user.id, user.display_name, user.email)
        return {
            "access_token": token,
            "user": {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
            },
        }
    finally:
        session.close()


@octile_router.post("/auth/forgot-password")
def auth_forgot_password(req: ForgotPasswordRequest):
    """Send a password reset OTP to the email."""
    email = _normalize_email(req.email)

    if _check_otp_rate_limit(email):
        return JSONResponse(
            status_code=429, content={"detail": "Too many attempts, try again later"}
        )

    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user or not user.is_verified:
            # Don't reveal whether email exists
            return {
                "status": "sent",
                "message": "If the email is registered, a reset code was sent",
            }

        otp = f"{secrets.randbelow(1000000):06d}"
        user.otp_code = otp
        user.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        session.commit()

        _send_otp_email(email, otp, purpose="reset")
        return {
            "status": "sent",
            "message": "If the email is registered, a reset code was sent",
        }
    finally:
        session.close()


@octile_router.post("/auth/reset-password")
def auth_reset_password(req: ResetPasswordRequest):
    """Reset password with OTP code."""
    email = _normalize_email(req.email)
    if len(req.new_password) < 6:
        return JSONResponse(
            status_code=400,
            content={"detail": "Password must be at least 6 characters"},
        )

    session = get_session()
    try:
        user = session.query(OctileUser).filter(OctileUser.email == email).first()
        if not user or not user.is_verified:
            return JSONResponse(
                status_code=404, content={"detail": "Account not found"}
            )
        if not user.otp_code or user.otp_code != req.otp_code.strip():
            return JSONResponse(
                status_code=400, content={"detail": "Invalid reset code"}
            )
        if user.otp_expires_at and user.otp_expires_at < datetime.utcnow():
            return JSONResponse(
                status_code=400, content={"detail": "Code expired, request a new one"}
            )

        user.password_hash = _pw_hasher.hash(req.new_password)
        user.otp_code = None
        user.otp_expires_at = None
        session.commit()

        return {"status": "ok", "message": "Password reset successfully"}
    finally:
        session.close()


@octile_router.get("/auth/me")
def auth_me(user: dict = Depends(require_octile_auth)):
    """Get current authenticated user info. Auto-refreshes JWT if past halfway."""
    session = get_session()
    try:
        db_user = (
            session.query(OctileUser).filter(OctileUser.id == int(user["sub"])).first()
        )
        result = {
            "id": int(user["sub"]),
            "display_name": db_user.display_name if db_user else user["name"],
            "email": user["email"],
            "picture": db_user.picture if db_user else None,
        }
        # Auto-refresh: if token is past halfway (>182 days old), issue new one
        iat = user.get("iat")
        if iat:
            issued = (
                datetime.fromtimestamp(iat, tz=timezone.utc)
                if isinstance(iat, (int, float))
                else iat
            )
            age_days = (datetime.now(timezone.utc) - issued).days
            if age_days > OCTILE_JWT_EXPIRY_DAYS // 2:
                result["refreshed_token"] = _create_octile_jwt(
                    int(user["sub"]),
                    db_user.display_name if db_user else user.get("name", ""),
                    user.get("email", ""),
                )
        return result
    finally:
        session.close()


# --- Google OAuth: ID token verification (Android Credential Manager) ---


class GoogleVerifyRequest(BaseModel):
    id_token: str
    browser_uuid: Optional[str] = None


@octile_router.post("/auth/google/verify")
def auth_google_verify(req: GoogleVerifyRequest):
    """Verify a Google ID token (from Android Credential Manager) and return a JWT."""
    if not OCTILE_GOOGLE_CLIENT_ID:
        return JSONResponse(
            status_code=501, content={"detail": "Google OAuth not configured"}
        )

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        idinfo = google_id_token.verify_oauth2_token(
            req.id_token, google_requests.Request(), OCTILE_GOOGLE_CLIENT_ID
        )
    except Exception as e:
        return JSONResponse(
            status_code=401, content={"detail": f"Invalid ID token: {e}"}
        )

    google_email = _normalize_email(idinfo.get("email", ""))
    google_name = idinfo.get("name", google_email.split("@")[0])
    google_picture = idinfo.get("picture", "")

    if not google_email:
        return JSONResponse(status_code=400, content={"detail": "No email in token"})

    browser_uuid = req.browser_uuid or ""
    session = get_session()
    try:
        user = (
            session.query(OctileUser).filter(OctileUser.email == google_email).first()
        )
        if not user:
            user = OctileUser(
                email=google_email,
                password_hash=_pw_hasher.hash(secrets.token_urlsafe(32)),
                display_name=google_name,
                picture=google_picture,
                browser_uuid=browser_uuid or None,
                is_verified=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            if not user.is_verified:
                # Pre-verification attack prevention: reset password so
                # attacker who pre-registered can't use their password
                user.is_verified = True
                user.password_hash = _pw_hasher.hash(secrets.token_urlsafe(32))
                user.display_name = google_name
            if browser_uuid and not user.browser_uuid:
                user.browser_uuid = browser_uuid
            if google_picture:
                user.picture = google_picture
            user.last_login_at = datetime.now(timezone.utc)
            session.commit()

        # Backfill anonymous scores from this device AND the stored device
        _backfill_scores_for_user(session, user.id, browser_uuid)
        if user.browser_uuid and user.browser_uuid != browser_uuid:
            _backfill_scores_for_user(session, user.id, user.browser_uuid)

        jwt_token = _create_octile_jwt(user.id, user.display_name, user.email)
    finally:
        session.close()

    return {
        "access_token": jwt_token,
        "display_name": user.display_name,
        "email": google_email,
        "picture": google_picture,
    }


# --- Google OAuth (server-side redirect flow) ---

# In-memory state tokens (short-lived, prevent CSRF)
_google_states: dict[str, float] = {}


@octile_router.get("/auth/google")
def auth_google_redirect(request: Request):
    """Redirect user to Google OAuth consent screen."""
    if not OCTILE_GOOGLE_CLIENT_ID or not OCTILE_GOOGLE_CLIENT_SECRET:
        return JSONResponse(
            status_code=501, content={"detail": "Google OAuth not configured"}
        )

    # Determine redirect URI: prefer env var, then worker URL, then auto-detect
    redirect_uri = OCTILE_GOOGLE_REDIRECT_URI
    if not redirect_uri:
        redirect_uri = OCTILE_WORKER_URL.rstrip("/") + "/auth/google/callback"
    if not redirect_uri or redirect_uri.endswith("/auth/google/callback") is False:
        redirect_uri = (
            str(request.base_url).rstrip("/") + "/octile/auth/google/callback"
        )

    # Detect source platform from query param (android or web)
    source = request.query_params.get("source", "web")
    return_url = request.query_params.get("return_url", "")
    browser_uuid = request.query_params.get("browser_uuid", "")

    # Generate state token
    state = secrets.token_urlsafe(32)
    _google_states[state] = _time.time()
    # Encode source, return_url, and browser_uuid in state
    state_with_source = state + "|" + source + "|" + return_url + "|" + browser_uuid

    # Clean old states (> 10 min)
    now = _time.time()
    expired = [k for k, v in _google_states.items() if now - v > 600]
    for k in expired:
        del _google_states[k]

    params = {
        "client_id": OCTILE_GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state_with_source,
        "prompt": "select_account",
    }
    import urllib.parse

    google_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    )
    return RedirectResponse(url=google_url)


@octile_router.get("/auth/google/callback")
def auth_google_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    """Handle Google OAuth callback: exchange code, create/find user, redirect with JWT."""
    import urllib.parse

    if error:
        return RedirectResponse(
            url=OCTILE_SITE_URL + "?auth_error=" + urllib.parse.quote(error)
        )

    if not code or not state:
        return RedirectResponse(url=OCTILE_SITE_URL + "?auth_error=missing_params")

    # Parse state (state_token:source:return_url:browser_uuid)
    parts = state.split("|", 3)
    state_token = parts[0]
    source = parts[1] if len(parts) > 1 else "web"
    return_url = parts[2] if len(parts) > 2 else ""
    browser_uuid = parts[3] if len(parts) > 3 else ""

    # Verify state token
    if state_token not in _google_states:
        err_url = return_url if return_url else OCTILE_SITE_URL
        return RedirectResponse(url=err_url + "?auth_error=invalid_state")
    del _google_states[state_token]

    # Determine redirect URI (must match the one used in /auth/google)
    redirect_uri = OCTILE_GOOGLE_REDIRECT_URI
    if not redirect_uri:
        redirect_uri = OCTILE_WORKER_URL.rstrip("/") + "/auth/google/callback"

    # Exchange authorization code for tokens
    import requests as http_requests

    try:
        token_resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": OCTILE_GOOGLE_CLIENT_ID,
                "client_secret": OCTILE_GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if token_resp.status_code != 200:
            return RedirectResponse(
                url=OCTILE_SITE_URL + "?auth_error=token_exchange_failed"
            )
        tokens = token_resp.json()
    except Exception:
        return RedirectResponse(
            url=OCTILE_SITE_URL + "?auth_error=token_exchange_failed"
        )

    # Verify the ID token
    id_token_str = tokens.get("id_token", "")
    if not id_token_str:
        return RedirectResponse(url=OCTILE_SITE_URL + "?auth_error=no_id_token")

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        idinfo = google_id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), OCTILE_GOOGLE_CLIENT_ID
        )
    except Exception:
        return RedirectResponse(url=OCTILE_SITE_URL + "?auth_error=invalid_id_token")

    google_email = _normalize_email(idinfo.get("email", ""))
    google_name = idinfo.get("name", google_email.split("@")[0])
    google_picture = idinfo.get("picture", "")

    if not google_email:
        return RedirectResponse(url=OCTILE_SITE_URL + "?auth_error=no_email")

    # Find or create OctileUser by email
    session = get_session()
    try:
        user = (
            session.query(OctileUser).filter(OctileUser.email == google_email).first()
        )
        if not user:
            # Auto-create verified account (Google already verified email)
            user = OctileUser(
                email=google_email,
                password_hash=_pw_hasher.hash(
                    secrets.token_urlsafe(32)
                ),  # random password
                display_name=google_name,
                picture=google_picture,
                browser_uuid=browser_uuid or None,
                is_verified=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            if not user.is_verified:
                # Pre-verification attack prevention: reset password
                user.is_verified = True
                user.password_hash = _pw_hasher.hash(secrets.token_urlsafe(32))
                user.display_name = google_name
            # Link browser_uuid if not already set
            if browser_uuid and not user.browser_uuid:
                user.browser_uuid = browser_uuid

        # Always update picture from Google (may change)
        if google_picture:
            user.picture = google_picture
        user.last_login_at = datetime.now(timezone.utc)
        session.commit()

        # Backfill anonymous scores from this device AND the stored device
        _backfill_scores_for_user(session, user.id, browser_uuid)
        if user.browser_uuid and user.browser_uuid != browser_uuid:
            _backfill_scores_for_user(session, user.id, user.browser_uuid)

        jwt_token = _create_octile_jwt(user.id, user.display_name, user.email)
    finally:
        session.close()

    # Redirect based on source
    encoded_name = urllib.parse.quote(google_name)
    if source == "android":
        # HTML+JS redirect: Chrome blocks server-side 307 to custom schemes
        deep_link = f"octile://auth?token={jwt_token}&name={encoded_name}"
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signing in…</title>
<style>body{{font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#1a1a2e;color:#fff;text-align:center}}
a{{color:#3498db;font-size:18px}}</style></head><body>
<div><p>Signing you in…</p><p><a href="{deep_link}">Tap here if the app doesn't open</a></p></div>
<script>location.replace("{deep_link}");</script></body></html>"""
        return HTMLResponse(content=html)
    else:
        # Web: redirect to return_url if provided, otherwise default site URL
        site_url = return_url if return_url else OCTILE_SITE_URL
        return RedirectResponse(
            url=f"{site_url}?auth_token={jwt_token}&auth_name={encoded_name}"
        )


# ---------------------------------------------------------------------------
# Progress sync endpoints
# ---------------------------------------------------------------------------


class SyncPushRequest(BaseModel):
    browser_uuid: Optional[str] = None
    level_easy: int = 0
    level_medium: int = 0
    level_hard: int = 0
    level_hell: int = 0
    exp: int = 0
    diamonds: int = 0
    chapters_completed: int = 0
    achievements: list = []
    streak_count: int = 0
    streak_last_date: Optional[str] = None
    months: list = []
    total_solved: int = 0
    total_time: float = 0
    grades_s: int = 0
    grades_a: int = 0
    grades_b: int = 0
    daily_tasks_date: Optional[str] = None
    daily_tasks_claimed: list = []
    daily_tasks_bonus_claimed: bool = False


def _merge_json_lists(server_json: str, client_list: list) -> str:
    """Union two JSON-encoded lists, return as JSON string."""
    import json

    try:
        server_list = json.loads(server_json or "[]")
    except (json.JSONDecodeError, TypeError):
        server_list = []
    merged = sorted(set(server_list) | set(client_list))
    return json.dumps(merged)


@octile_router.post("/sync/push")
def sync_push(req: SyncPushRequest, user: dict = Depends(require_octile_auth)):
    """Push local progress to server. Merges with MAX strategy."""
    user_id = int(user["sub"])
    session = get_session()
    try:
        prog = (
            session.query(OctileProgress)
            .filter(OctileProgress.user_id == user_id)
            .first()
        )
        if not prog:
            prog = OctileProgress(user_id=user_id)
            session.add(prog)

        # Link browser_uuid if provided
        if req.browser_uuid:
            prog.browser_uuid = req.browser_uuid

        # MAX for numeric fields
        prog.level_easy = max(prog.level_easy or 0, req.level_easy)
        prog.level_medium = max(prog.level_medium or 0, req.level_medium)
        prog.level_hard = max(prog.level_hard or 0, req.level_hard)
        prog.level_hell = max(prog.level_hell or 0, req.level_hell)
        prog.exp = max(prog.exp or 0, req.exp)
        prog.diamonds = max(prog.diamonds or 0, req.diamonds)
        prog.chapters_completed = max(
            prog.chapters_completed or 0, req.chapters_completed
        )
        prog.total_solved = max(prog.total_solved or 0, req.total_solved)
        prog.total_time = max(prog.total_time or 0, req.total_time)
        prog.grades_s = max(prog.grades_s or 0, req.grades_s)
        prog.grades_a = max(prog.grades_a or 0, req.grades_a)
        prog.grades_b = max(prog.grades_b or 0, req.grades_b)

        # Union for list fields
        prog.achievements = _merge_json_lists(prog.achievements, req.achievements)
        prog.months = _merge_json_lists(prog.months, req.months)

        # Streak: keep higher count or more recent date
        if req.streak_count > (prog.streak_count or 0) or (
            req.streak_count == (prog.streak_count or 0)
            and (req.streak_last_date or "") >= (prog.streak_last_date or "")
        ):
            prog.streak_count = req.streak_count
            prog.streak_last_date = req.streak_last_date

        # Daily tasks: if client date is newer or same, merge claimed lists
        if req.daily_tasks_date and (
            req.daily_tasks_date >= (prog.daily_tasks_date or "")
        ):
            prog.daily_tasks_date = req.daily_tasks_date
            prog.daily_tasks_claimed = _merge_json_lists(
                prog.daily_tasks_claimed or "[]", req.daily_tasks_claimed
            )
            prog.daily_tasks_bonus_claimed = max(
                prog.daily_tasks_bonus_claimed or 0,
                1 if req.daily_tasks_bonus_claimed else 0,
            )

        prog.updated_at = datetime.now(timezone.utc)
        session.commit()

        # Backfill anonymous scores from this device
        if req.browser_uuid:
            _backfill_scores_for_user(session, user_id, req.browser_uuid)

        return {"status": "ok"}
    finally:
        session.close()


@octile_router.get("/sync/pull")
def sync_pull(user: dict = Depends(require_octile_auth)):
    """Pull server progress to client."""
    import json

    user_id = int(user["sub"])
    session = get_session()
    try:
        prog = (
            session.query(OctileProgress)
            .filter(OctileProgress.user_id == user_id)
            .first()
        )
        if not prog:
            return {"status": "empty"}

        return {
            "status": "ok",
            "progress": {
                "level_easy": prog.level_easy or 0,
                "level_medium": prog.level_medium or 0,
                "level_hard": prog.level_hard or 0,
                "level_hell": prog.level_hell or 0,
                "exp": prog.exp or 0,
                "diamonds": prog.diamonds or 0,
                "chapters_completed": prog.chapters_completed or 0,
                "achievements": json.loads(prog.achievements or "[]"),
                "streak_count": prog.streak_count or 0,
                "streak_last_date": prog.streak_last_date,
                "months": json.loads(prog.months or "[]"),
                "total_solved": prog.total_solved or 0,
                "total_time": prog.total_time or 0,
                "grades_s": prog.grades_s or 0,
                "grades_a": prog.grades_a or 0,
                "grades_b": prog.grades_b or 0,
                "daily_tasks_date": prog.daily_tasks_date,
                "daily_tasks_claimed": json.loads(prog.daily_tasks_claimed or "[]"),
                "daily_tasks_bonus_claimed": bool(prog.daily_tasks_bonus_claimed),
            },
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Player stats + ELO endpoints
# ---------------------------------------------------------------------------


@octile_router.get("/player/{uuid}/stats")
def get_player_stats(uuid: str):
    """Get aggregated stats for a player from server-side score data."""
    session = get_session()
    try:
        # Overall stats
        overall = (
            session.query(
                func.sum(OctileScore.exp).label("total_exp"),
                func.sum(OctileScore.diamonds).label("total_diamonds"),
                func.count(func.distinct(OctileScore.puzzle_number)).label(
                    "puzzles_solved"
                ),
                func.avg(OctileScore.resolve_time).label("avg_time"),
                func.count(OctileScore.id).label("total_solves"),
            )
            .filter(OctileScore.browser_uuid == uuid, OctileScore.flagged == 0)
            .first()
        )

        if not overall or not overall.total_solves:
            return {"status": "empty"}

        # Per-difficulty breakdown
        by_diff_rows = (
            session.query(
                OctileScore.puzzle_number,
                OctileScore.resolve_time,
                OctileScore.exp,
            )
            .filter(OctileScore.browser_uuid == uuid, OctileScore.flagged == 0)
            .all()
        )

        by_difficulty = {}
        for pn, rt, xp in by_diff_rows:
            try:
                d = get_puzzle_difficulty(pn)
            except Exception:
                continue
            label = DIFFICULTY_LABELS.get(d, "unknown")
            if label not in by_difficulty:
                by_difficulty[label] = {"count": 0, "total_time": 0.0, "total_exp": 0}
            by_difficulty[label]["count"] += 1
            by_difficulty[label]["total_time"] += rt
            by_difficulty[label]["total_exp"] += xp

        for label, stats in by_difficulty.items():
            stats["avg_time"] = (
                round(stats["total_time"] / stats["count"], 1) if stats["count"] else 0
            )
            del stats["total_time"]

        # Grade distribution (computed from scores)
        grades = {"S": 0, "A": 0, "B": 0}
        for pn, rt, _ in by_diff_rows:
            try:
                d = get_puzzle_difficulty(pn)
            except Exception:
                continue
            g = calc_skill_grade(d, rt)
            grades[g] += 1

        # ELO
        elo = calc_elo_for_player(session, uuid)

        return {
            "status": "ok",
            "total_exp": overall.total_exp or 0,
            "total_diamonds": overall.total_diamonds or 0,
            "puzzles_solved": overall.puzzles_solved or 0,
            "avg_time": round(overall.avg_time, 1) if overall.avg_time else 0,
            "by_difficulty": by_difficulty,
            "grade_distribution": grades,
            "elo": elo,
        }
    finally:
        session.close()


@octile_router.get("/player/{uuid}/elo")
def get_player_elo(uuid: str):
    """Get ELO rating for a player."""
    session = get_session()
    try:
        count = (
            session.query(func.count(OctileScore.id))
            .filter(OctileScore.browser_uuid == uuid, OctileScore.flagged == 0)
            .scalar()
        )
        if not count:
            return {"elo": ELO_INITIAL, "solves": 0}
        elo = calc_elo_for_player(session, uuid)
        return {"elo": elo, "solves": count}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Analytics — user-agent parsing and distribution endpoint
# ---------------------------------------------------------------------------


def _parse_ua(ua: str) -> dict:
    """Parse a user-agent string into platform, os, and browser."""
    if not ua:
        return {"platform": "Unknown", "os": "Unknown", "browser": "Unknown"}

    # OS detection
    if "Android" in ua:
        m = _re.search(r"Android\s*([\d.]+)", ua)
        os_name = "Android " + m.group(1) if m else "Android"
        platform = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        m = _re.search(r"OS\s+([\d_]+)", ua)
        ver = m.group(1).replace("_", ".") if m else ""
        os_name = "iOS " + ver if ver else "iOS"
        platform = "iOS"
    elif "Windows" in ua:
        m = _re.search(r"Windows NT\s*([\d.]+)", ua)
        nt_map = {"10.0": "10/11", "6.3": "8.1", "6.2": "8", "6.1": "7"}
        ver = nt_map.get(m.group(1), m.group(1)) if m else ""
        os_name = "Windows " + ver if ver else "Windows"
        platform = "Desktop"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        m = _re.search(r"Mac OS X\s+([\d_.]+)", ua)
        ver = m.group(1).replace("_", ".") if m else ""
        os_name = "macOS " + ver if ver else "macOS"
        platform = "Desktop"
    elif "Linux" in ua:
        os_name = "Linux"
        platform = "Desktop"
    elif "CrOS" in ua:
        os_name = "ChromeOS"
        platform = "Desktop"
    else:
        os_name = "Unknown"
        platform = "Unknown"

    # Browser detection (order matters)
    if "OctileAndroid" in ua or "OctileApp" in ua:
        browser = "Octile App"
        platform = "Android"
    elif "Edg/" in ua:
        m = _re.search(r"Edg/([\d.]+)", ua)
        browser = "Edge " + m.group(1).split(".")[0] if m else "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua:
        m = _re.search(r"Firefox/([\d.]+)", ua)
        browser = "Firefox " + m.group(1).split(".")[0] if m else "Firefox"
    elif "CriOS/" in ua:
        browser = "Chrome (iOS)"
    elif "Chrome/" in ua:
        m = _re.search(r"Chrome/([\d.]+)", ua)
        browser = "Chrome " + m.group(1).split(".")[0] if m else "Chrome"
    elif "Safari/" in ua and "Version/" in ua:
        m = _re.search(r"Version/([\d.]+)", ua)
        browser = "Safari " + m.group(1).split(".")[0] if m else "Safari"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "Other"

    return {"platform": platform, "os": os_name, "browser": browser}


@octile_router.get("/analytics")
def get_analytics():
    """Return user distribution by platform, OS, and browser."""
    session = get_session()
    try:
        # Get distinct (browser_uuid, user_agent) pairs — latest UA per user
        subq = (
            session.query(
                OctileScore.browser_uuid,
                OctileScore.user_agent,
                func.max(OctileScore.created_at).label("last_seen"),
            )
            .filter(OctileScore.user_agent.isnot(None), OctileScore.user_agent != "")
            .group_by(OctileScore.browser_uuid)
            .all()
        )

        platform_counts = {}
        os_counts = {}
        browser_counts = {}
        players = []

        for row in subq:
            parsed = _parse_ua(row.user_agent)
            p, o, b = parsed["platform"], parsed["os"], parsed["browser"]
            platform_counts[p] = platform_counts.get(p, 0) + 1
            os_counts[o] = os_counts.get(o, 0) + 1
            browser_counts[b] = browser_counts.get(b, 0) + 1
            players.append(
                {
                    "uuid": row.browser_uuid[:8] + "…",
                    "platform": p,
                    "os": o,
                    "browser": b,
                    "last_seen": row.last_seen.isoformat() if row.last_seen else "",
                    "ua": row.user_agent[:120] if row.user_agent else "",
                }
            )

        # Sort by count descending
        def _sorted(d):
            return sorted(d.items(), key=lambda x: -x[1])

        # Total unique players (including those without UA)
        total_players = session.query(
            func.count(func.distinct(OctileScore.browser_uuid))
        ).scalar()
        total_scores = session.query(func.count(OctileScore.id)).scalar()

        return {
            "total_players": total_players,
            "total_scores": total_scores,
            "players_with_ua": len(subq),
            "platform": _sorted(platform_counts),
            "os": _sorted(os_counts),
            "browser": _sorted(browser_counts),
            "players": sorted(players, key=lambda x: x["last_seen"], reverse=True),
        }
    finally:
        session.close()


@octile_router.get("/analytics/dashboard")
def analytics_dashboard():
    """Serve the analytics dashboard HTML."""
    import pathlib

    html_path = pathlib.Path(__file__).parent / "octile_analytics.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# League endpoints
# ---------------------------------------------------------------------------

_TEAM_NAME_GEMS = [
    "Diamond",
    "Topaz",
    "Citrine",
    "Garnet",
    "Opal",
    "Pearl",
    "Jade",
    "Onyx",
    "Quartz",
    "Agate",
    "Zircon",
    "Beryl",
    "Coral",
    "Jasper",
    "Lapis",
    "Pyrite",
    "Malachite",
    "Turquoise",
    "Peridot",
    "Tanzanite",
]
_TEAM_NAME_ANIMALS = [
    "Wolves",
    "Eagles",
    "Panthers",
    "Hawks",
    "Foxes",
    "Dragons",
    "Tigers",
    "Bears",
    "Falcons",
    "Lions",
    "Owls",
    "Phoenix",
    "Cobras",
    "Stags",
    "Ravens",
    "Vipers",
    "Lynx",
    "Sharks",
]


def _gen_team_name():
    import random

    return random.choice(_TEAM_NAME_GEMS) + " " + random.choice(_TEAM_NAME_ANIMALS)


def _league_assign_team(session, user_id, tier):
    """Assign user to a team for the current month. Creates a new team if needed."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    team_size = LEAGUE_TIERS.get(tier, LEAGUE_TIERS[0])["team_size"]

    # Find a team with open slots
    teams = (
        session.query(LeagueTeam)
        .filter(LeagueTeam.tier == tier, LeagueTeam.month == current_month)
        .all()
    )
    for team in teams:
        member_count = (
            session.query(func.count(LeagueMember.user_id))
            .filter(LeagueMember.team_id == team.id)
            .scalar()
        )
        if member_count < team_size:
            return team.id

    # No open team — create new one
    new_team = LeagueTeam(tier=tier, month=current_month, team_name=_gen_team_name())
    session.add(new_team)
    session.flush()
    return new_team.id


@octile_router.post("/league/join")
def league_join(user: dict = Depends(require_octile_auth)):
    user_id = int(user["sub"])
    session = get_session()
    try:
        existing = (
            session.query(LeagueMember).filter(LeagueMember.user_id == user_id).first()
        )
        if existing:
            tier_info = LEAGUE_TIERS.get(existing.tier, LEAGUE_TIERS[0])
            return {
                "status": "already_joined",
                "tier": existing.tier,
                "tier_name": tier_info["name_en"],
                "team_id": existing.team_id,
            }

        member = LeagueMember(user_id=user_id, tier=0)
        session.add(member)
        session.flush()
        team_id = _league_assign_team(session, user_id, 0)
        member.team_id = team_id
        session.add(
            LeagueHistory(
                user_id=user_id,
                event="join",
                to_tier=0,
                date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
        )
        session.commit()
        return {
            "status": "ok",
            "tier": 0,
            "tier_name": "Bronze",
            "team_id": team_id,
        }
    finally:
        session.close()


@octile_router.get("/league/my-team")
def league_my_team(user: dict = Depends(require_octile_auth)):
    user_id = int(user["sub"])
    session = get_session()
    try:
        member = (
            session.query(LeagueMember).filter(LeagueMember.user_id == user_id).first()
        )
        if not member:
            return {"status": "not_joined"}
        if not member.team_id:
            return {"status": "no_team"}

        tier_info = LEAGUE_TIERS.get(member.tier, LEAGUE_TIERS[0])

        # Get all team members
        teammates = (
            session.query(LeagueMember)
            .filter(LeagueMember.team_id == member.team_id)
            .all()
        )

        # Look up display names and pictures
        user_ids = [m.user_id for m in teammates]
        users = session.query(OctileUser).filter(OctileUser.id.in_(user_ids)).all()
        user_map = {u.id: u for u in users}

        # Build member list sorted by today_exp descending
        members_data = []
        for m in teammates:
            u = user_map.get(m.user_id)
            members_data.append(
                {
                    "user_id": m.user_id,
                    "display_name": u.display_name if u else None,
                    "picture": u.picture if u else None,
                    "exp_today": m.today_exp or 0,
                    "inactive_days": m.inactive_days or 0,
                }
            )
        members_data.sort(key=lambda x: x["exp_today"], reverse=True)
        for i, m in enumerate(members_data):
            m["position"] = i + 1

        # My position
        my_pos = next(
            (m["position"] for m in members_data if m["user_id"] == user_id), 0
        )

        # Team info
        team = session.query(LeagueTeam).filter(LeagueTeam.id == member.team_id).first()

        return {
            "status": "ok",
            "tier": member.tier,
            "tier_name": tier_info["name_en"],
            "tier_name_zh": tier_info["name_zh"],
            "tier_color": tier_info["color"],
            "team_id": member.team_id,
            "team_name": team.team_name if team else "",
            "month": team.month if team else "",
            "my_position": my_pos,
            "my_exp_today": member.today_exp or 0,
            "promo_streak": member.promo_streak or 0,
            "demote_streak": member.demote_streak or 0,
            "active_count": sum(
                1 for m in members_data if (m.get("inactive_days") or 0) < 2
            ),
            "min_active": LEAGUE_MIN_ACTIVE_FOR_EVAL,
            "min_exp_for_promo": LEAGUE_MIN_EXP_FOR_PROMO,
            "members": members_data,
        }
    finally:
        session.close()


@octile_router.get("/league/history")
def league_history(user: dict = Depends(require_octile_auth)):
    user_id = int(user["sub"])
    session = get_session()
    try:
        events = (
            session.query(LeagueHistory)
            .filter(LeagueHistory.user_id == user_id)
            .order_by(LeagueHistory.created_at.desc())
            .limit(30)
            .all()
        )
        return {
            "status": "ok",
            "events": [
                {
                    "event": e.event,
                    "from_tier": e.from_tier,
                    "to_tier": e.to_tier,
                    "from_name": LEAGUE_TIERS.get(e.from_tier, {}).get("name_en")
                    if e.from_tier is not None
                    else None,
                    "to_name": LEAGUE_TIERS.get(e.to_tier, {}).get("name_en")
                    if e.to_tier is not None
                    else None,
                    "date": e.date,
                }
                for e in events
            ],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# League daily scheduler
# ---------------------------------------------------------------------------


def league_daily_evaluation():
    """Run daily at ~00:05 UTC: snapshot EXP, evaluate promotion/demotion, reset."""
    session = get_session()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        all_members = (
            session.query(LeagueMember).filter(LeagueMember.team_id.isnot(None)).all()
        )

        # 1. Snapshot today_exp and track inactive
        for m in all_members:
            # Snapshot to history table
            existing = (
                session.query(LeagueDailyExp)
                .filter(
                    LeagueDailyExp.user_id == m.user_id, LeagueDailyExp.date == today
                )
                .first()
            )
            if not existing:
                session.add(
                    LeagueDailyExp(
                        user_id=m.user_id,
                        team_id=m.team_id,
                        date=today,
                        exp=m.today_exp or 0,
                    )
                )

            # Inactive tracking
            if (m.today_exp or 0) == 0:
                m.inactive_days = (m.inactive_days or 0) + 1
            else:
                m.inactive_days = 0

        # 2. Evaluate per team
        members_by_team = defaultdict(list)
        for m in all_members:
            if m.team_id:
                members_by_team[m.team_id].append(m)

        for team_id, members in members_by_team.items():
            # Filter active members for ranking
            active = [m for m in members if (m.inactive_days or 0) < 2]
            active.sort(key=lambda m: m.today_exp or 0, reverse=True)

            # Skip evaluation if not enough active members (cold-start protection)
            if len(active) < LEAGUE_MIN_ACTIVE_FOR_EVAL:
                for m in active:
                    m.last_eval_date = today
                continue

            for rank, m in enumerate(active):
                if m.last_eval_date == today:
                    continue

                # Anti-cheat
                if (m.today_exp or 0) > LEAGUE_DAILY_EXP_CAP:
                    m.last_eval_date = today
                    continue

                # Safety zone: top N for promotion
                # Must also meet minimum EXP threshold to prevent idle promotion
                if (
                    rank < LEAGUE_PROMO_TOP_N
                    and (m.today_exp or 0) >= LEAGUE_MIN_EXP_FOR_PROMO
                ):
                    m.promo_streak = (m.promo_streak or 0) + 1
                    m.demote_streak = 0
                # Last place for demotion
                elif rank == len(active) - 1:
                    m.demote_streak = (m.demote_streak or 0) + 1
                    m.promo_streak = 0
                else:
                    m.promo_streak = 0
                    m.demote_streak = 0

                m.last_eval_date = today

                # Promote?
                if (m.promo_streak or 0) >= LEAGUE_PROMO_DAYS and m.tier < 7:
                    old_tier = m.tier
                    m.tier += 1
                    m.promo_streak = 0
                    session.add(
                        LeagueHistory(
                            user_id=m.user_id,
                            event="promote",
                            from_tier=old_tier,
                            to_tier=m.tier,
                            date=today,
                        )
                    )

                # Demote?
                if (m.demote_streak or 0) >= LEAGUE_DEMOTE_DAYS and m.tier > 0:
                    old_tier = m.tier
                    m.tier -= 1
                    m.demote_streak = 0
                    session.add(
                        LeagueHistory(
                            user_id=m.user_id,
                            event="demote",
                            from_tier=old_tier,
                            to_tier=m.tier,
                            date=today,
                        )
                    )

            # Reset inactive members' streaks
            for m in members:
                if (m.inactive_days or 0) >= 2 and m.last_eval_date != today:
                    m.promo_streak = 0
                    m.demote_streak = 0
                    m.last_eval_date = today

        # 3. Reset today_exp atomically — use BEGIN IMMEDIATE to block
        # concurrent score submits from incrementing during the reset window
        session.commit()  # commit evaluation results first
        session.execute(sql_text("BEGIN IMMEDIATE"))
        session.execute(sql_text("UPDATE league_members SET today_exp = 0"))
        session.execute(sql_text("COMMIT"))

        # 4. Prune old daily_exp (keep 7 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        session.query(LeagueDailyExp).filter(LeagueDailyExp.date < cutoff).delete()

        session.commit()
    except Exception as e:
        session.rollback()
        import logging

        logging.getLogger("octile").error(f"League daily evaluation failed: {e}")
    finally:
        session.close()


def league_monthly_reassign():
    """Run on 1st of each month: reassign all members to new teams."""
    session = get_session()
    try:
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check if already reassigned this month
        existing_teams = (
            session.query(LeagueTeam).filter(LeagueTeam.month == current_month).count()
        )
        if existing_teams > 0:
            return  # Already done

        all_members = session.query(LeagueMember).all()
        if not all_members:
            return

        # Group by tier, sub-sort by recent activity
        by_tier = defaultdict(list)
        for m in all_members:
            # Get 7-day EXP for activity sorting
            recent_exp = (
                session.query(func.coalesce(func.sum(LeagueDailyExp.exp), 0))
                .filter(LeagueDailyExp.user_id == m.user_id)
                .scalar()
            )
            by_tier[m.tier].append((m, recent_exp))

        for tier, members_with_exp in by_tier.items():
            # Sort by activity (most active first), then shuffle within activity bands
            members_with_exp.sort(key=lambda x: x[1], reverse=True)
            members = [m for m, _ in members_with_exp]

            team_size = LEAGUE_TIERS.get(tier, LEAGUE_TIERS[0])["team_size"]

            # Smart sizing: avoid tiny last team
            n = len(members)
            if n <= team_size:
                chunks = [members]
            else:
                full_teams = n // team_size
                remainder = n % team_size
                if remainder > 0 and remainder < team_size // 2:
                    # Distribute remainder: make last 2 teams more even
                    chunks = []
                    idx = 0
                    for i in range(full_teams - 1):
                        chunks.append(members[idx : idx + team_size])
                        idx += team_size
                    # Split remaining evenly
                    rest = members[idx:]
                    mid = len(rest) // 2
                    chunks.append(rest[:mid])
                    chunks.append(rest[mid:])
                else:
                    chunks = [
                        members[i : i + team_size] for i in range(0, n, team_size)
                    ]

            for chunk in chunks:
                if not chunk:
                    continue
                team = LeagueTeam(
                    tier=tier, month=current_month, team_name=_gen_team_name()
                )
                session.add(team)
                session.flush()
                for m in chunk:
                    m.team_id = team.id
                    m.promo_streak = 0
                    m.demote_streak = 0
                    m.inactive_days = 0
                    m.last_eval_date = None
                session.add(
                    LeagueHistory(
                        user_id=chunk[0].user_id,
                        event="reassign",
                        from_tier=tier,
                        to_tier=tier,
                        date=today,
                    )
                )

        session.commit()
    except Exception as e:
        session.rollback()
        import logging

        logging.getLogger("octile").error(f"League monthly reassignment failed: {e}")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------

OCTILE_FEEDBACK_EMAIL = "octileapp@googlegroups.com"


class FeedbackRequest(BaseModel):
    type: str  # bug, feature, general
    email: Optional[str] = None
    message: str
    lang: Optional[str] = "en"
    version: Optional[str] = None
    platform: Optional[str] = None
    display_name: Optional[str] = None
    browser_uuid: Optional[str] = None
    device: Optional[str] = None
    screenshot: Optional[str] = None  # data:image/...;base64,...
    screenshot_name: Optional[str] = None


@octile_router.post("/feedback")
def submit_feedback(req: FeedbackRequest, request: Request):
    """Receive user feedback and email it to the team."""
    msg = req.message.strip()
    if not msg or len(msg) < 3:
        return JSONResponse({"detail": "Message too short"}, status_code=400)
    if len(msg) > 5000:
        return JSONResponse({"detail": "Message too long"}, status_code=400)
    if req.type not in ("bug", "feature", "general"):
        return JSONResponse({"detail": "Invalid type"}, status_code=400)

    sender = _get_email_sender()
    if not sender:
        return JSONResponse({"detail": "Feedback service unavailable"}, status_code=503)

    client_ip = request.headers.get(
        "X-Real-IP", request.client.host if request.client else "unknown"
    )
    type_label = {
        "bug": "Bug Report",
        "feature": "Feature Request",
        "general": "General Feedback",
    }.get(req.type, req.type)
    subject = f"[Octile Feedback] {type_label}"

    body = f"""Type: {type_label}
From: {req.email or "(anonymous)"}
Name: {req.display_name or "(anonymous)"}
Language: {req.lang or "en"}
Version: {req.version or "unknown"}
UUID: {req.browser_uuid or "unknown"}
Device: {req.device or "unknown"}
IP: {client_ip}
Platform: {(req.platform or "unknown")[:200]}

---
{msg}
"""

    # Decode screenshot if provided, save to temp file for attachment
    attachments = []
    if req.screenshot and req.screenshot.startswith("data:image/"):
        import base64
        import tempfile

        try:
            # data:image/png;base64,iVBOR...
            header, b64data = req.screenshot.split(",", 1)
            ext = "png" if "png" in header else "jpg"
            img_bytes = base64.b64decode(b64data)
            if len(img_bytes) <= 5 * 1024 * 1024:  # 5 MB limit
                suffix = f"_{req.screenshot_name}" if req.screenshot_name else f".{ext}"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(img_bytes)
                tmp.close()
                attachments.append(tmp.name)
        except Exception:
            pass  # skip bad screenshot silently

    result = sender.send_email(
        to_email=OCTILE_FEEDBACK_EMAIL,
        subject=subject,
        body=body,
        is_html=False,
        attachments=attachments if attachments else None,
    )

    # Clean up temp files
    for f in attachments:
        try:
            import os as _os

            _os.unlink(f)
        except Exception:
            pass

    if result.get("status") == "success":
        return {"status": "ok"}
    return JSONResponse({"detail": "Failed to send feedback"}, status_code=500)
