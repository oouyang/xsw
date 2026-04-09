#!/usr/bin/env python3
"""
Puzzle analysis script for Octile v2 reordering.

Computes per-puzzle metrics:
  - Geometric theme classification (perimeter / split / holes / chaos)
  - Solution count (capped at 100, using backtracking solver)
  - Pocket analysis (Hell only — bad pockets that don't match any piece size)

Outputs: xsw/puzzle_analysis.json
"""

import json
import multiprocessing
import os
import sys
import time
from collections import deque

# Add parent dir so we can import octile modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from octile_puzzle_data import PUZZLE_DATA
from octile_api import P92_MAP

PUZZLE_COUNT = 11378
BOARD_SIZE = 8
TOTAL_CELLS = 64

# Player piece sizes (for pocket analysis)
PLAYER_PIECE_SIZES = frozenset({4, 5, 6, 8, 9, 10, 12})

# Solver pieces: ordered largest to smallest for efficiency
# (rows, cols) for each orientation
SOLVER_PIECES = [
    # b2: 3x4 / 4x3 = 12 cells
    [(3, 4), (4, 3)],
    # b1: 2x5 / 5x2 = 10 cells
    [(2, 5), (5, 2)],
    # y1: 3x3 = 9 cells
    [(3, 3)],
    # y2: 2x4 / 4x2 = 8 cells
    [(2, 4), (4, 2)],
    # r1: 2x3 / 3x2 = 6 cells
    [(2, 3), (3, 2)],
    # w1: 1x5 / 5x1 = 5 cells
    [(1, 5), (5, 1)],
    # r2: 1x4 / 4x1 = 4 cells
    [(1, 4), (4, 1)],
    # w2: 2x2 = 4 cells
    [(2, 2)],
]


def decode_puzzle_cells(index):
    """Decode puzzle at 0-based index, returns set of 6 grey cell indices."""
    data = PUZZLE_DATA
    o = index * 3
    n = P92_MAP[data[o]] + P92_MAP[data[o + 1]] * 92 + P92_MAP[data[o + 2]] * 92 * 92

    g3_idx = n % 96
    g2_idx = (n // 96) % 112
    g1 = n // 10752

    if g2_idx < 56:
        r, c = divmod(g2_idx, 7)
        g2a = r * 8 + c
        g2b = g2a + 1
    else:
        i = g2_idx - 56
        r, c = divmod(i, 8)
        g2a = r * 8 + c
        g2b = g2a + 8

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
# Theme classification
# ---------------------------------------------------------------------------

def is_edge_cell(cell):
    """Check if cell is on the board perimeter (row 0/7 or col 0/7)."""
    r, c = divmod(cell, 8)
    return r == 0 or r == 7 or c == 0 or c == 7


def get_4neighbors(cell):
    """Return 4-adjacent neighbors of cell on 8x8 board."""
    r, c = divmod(cell, 8)
    neighbors = []
    if r > 0:
        neighbors.append((r - 1) * 8 + c)
    if r < 7:
        neighbors.append((r + 1) * 8 + c)
    if c > 0:
        neighbors.append(r * 8 + c - 1)
    if c < 7:
        neighbors.append(r * 8 + c + 1)
    return neighbors


def flood_fill_count(free_cells_set, start):
    """Flood fill from start, return set of reachable cells."""
    visited = set()
    queue = deque([start])
    visited.add(start)
    while queue:
        cell = queue.popleft()
        for nb in get_4neighbors(cell):
            if nb in free_cells_set and nb not in visited:
                visited.add(nb)
                queue.append(nb)
    return visited


def is_split(grey_set):
    """Check if grey cells split the free space into 2+ disconnected regions,
    OR if all grey cells share a single row or column."""
    free = set(range(64)) - grey_set
    if not free:
        return False

    # Flood fill from first free cell
    start = next(iter(free))
    reached = flood_fill_count(free, start)
    if len(reached) < len(free):
        return True

    # Also classify as split if all grey cells share a row or column
    rows = set(c // 8 for c in grey_set)
    cols = set(c % 8 for c in grey_set)
    if len(rows) == 1 or len(cols) == 1:
        return True

    return False


def is_holes(grey_cells):
    """Check that the 3 grey pieces are mutually non-adjacent.
    grey_cells = [g1, g2a, g2b, g3a, g3b, g3c]"""
    piece1 = {grey_cells[0]}
    piece2 = {grey_cells[1], grey_cells[2]}
    piece3 = {grey_cells[3], grey_cells[4], grey_cells[5]}

    def pieces_adjacent(a, b):
        for cell_a in a:
            nb = set(get_4neighbors(cell_a))
            if nb & b:
                return True
        return False

    if pieces_adjacent(piece1, piece2):
        return False
    if pieces_adjacent(piece1, piece3):
        return False
    if pieces_adjacent(piece2, piece3):
        return False
    return True


def classify_theme(grey_cells):
    """Classify puzzle into theme: perimeter, split, holes, chaos."""
    grey_set = set(grey_cells)

    # Perimeter: at least 5 of 6 grey cells on board edge
    edge_count = sum(1 for c in grey_cells if is_edge_cell(c))
    if edge_count >= 5:
        return "perimeter"

    # Split: free space disconnected or grey cells form wall
    if is_split(grey_set):
        return "split"

    # Holes: all 3 grey pieces mutually non-adjacent
    if is_holes(grey_cells):
        return "holes"

    return "chaos"


# ---------------------------------------------------------------------------
# Solution counting (backtracking solver)
# ---------------------------------------------------------------------------

def count_solutions(board, pieces_remaining, cap=100):
    """Count solutions via backtracking. board is 64-element list (0=free, 1=occupied).
    Returns count capped at `cap`."""
    if not pieces_remaining:
        return 1

    # Find first free cell
    first_free = -1
    for i in range(64):
        if board[i] == 0:
            first_free = i
            break
    if first_free == -1:
        return 1

    count = 0
    # Try each remaining piece at each orientation at the first free cell's row
    fr, fc = divmod(first_free, 8)

    for pi, orientations in enumerate(pieces_remaining):
        remaining = pieces_remaining[:pi] + pieces_remaining[pi + 1:]
        for rows, cols in orientations:
            # Try all positions where this piece could cover first_free
            for pr in range(rows):
                for pc in range(cols):
                    # Top-left of piece placement
                    tr = fr - pr
                    tc = fc - pc
                    if tr < 0 or tc < 0 or tr + rows > 8 or tc + cols > 8:
                        continue
                    # Check all cells
                    cells = []
                    ok = True
                    for dr in range(rows):
                        for dc in range(cols):
                            idx = (tr + dr) * 8 + (tc + dc)
                            if board[idx] != 0:
                                ok = False
                                break
                            cells.append(idx)
                        if not ok:
                            break
                    if not ok:
                        continue
                    # Place piece
                    for idx in cells:
                        board[idx] = 1
                    count += count_solutions(board, remaining, cap - count)
                    # Unplace
                    for idx in cells:
                        board[idx] = 0
                    if count >= cap:
                        return cap
    return count


def solve_puzzle_count(puzzle_index):
    """Count solutions for a single puzzle (0-based index). Returns (index, count)."""
    grey_cells = decode_puzzle_cells(puzzle_index)
    board = [0] * 64
    for c in grey_cells:
        board[c] = 1
    n = count_solutions(board, SOLVER_PIECES, cap=100)
    return puzzle_index, n


# ---------------------------------------------------------------------------
# Pocket analysis (Hell only)
# ---------------------------------------------------------------------------

def compute_pocket_score(grey_cells):
    """Count connected regions of free cells whose size doesn't match any piece size."""
    grey_set = set(grey_cells)
    free = set(range(64)) - grey_set
    visited = set()
    bad_pockets = 0

    for cell in free:
        if cell in visited:
            continue
        region = flood_fill_count(free, cell)
        visited |= region
        if len(region) not in PLAYER_PIECE_SIZES:
            bad_pockets += 1

    return bad_pockets


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def analyze_batch(indices):
    """Analyze a batch of puzzle indices. Returns list of (index, solution_count)."""
    results = []
    for idx in indices:
        _, count = solve_puzzle_count(idx)
        results.append((idx, count))
    return results


def main():
    start_time = time.time()

    # Load difficulty data for pocket analysis (Hell = level 4)
    data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "difficulty_levels.json")
    with open(data_path) as f:
        diff_data = json.load(f)
    levels = diff_data["levels"]

    print(f"Analyzing {PUZZLE_COUNT} puzzles...")

    # Step 1: Theme classification (fast, single-threaded)
    print("Step 1/3: Theme classification...")
    themes = []
    theme_counts = {"perimeter": 0, "split": 0, "holes": 0, "chaos": 0}
    for i in range(PUZZLE_COUNT):
        grey_cells = decode_puzzle_cells(i)
        theme = classify_theme(grey_cells)
        themes.append(theme)
        theme_counts[theme] += 1
        if (i + 1) % 2000 == 0:
            print(f"  {i + 1}/{PUZZLE_COUNT} classified")

    print(f"  Theme distribution: {theme_counts}")

    # Check for skewed themes
    for theme, count in theme_counts.items():
        pct = count / PUZZLE_COUNT * 100
        if pct < 5:
            print(f"  WARNING: '{theme}' has only {count} puzzles ({pct:.1f}%)")

    # Per-level theme distribution
    level_names = {1: "easy", 2: "medium", 3: "hard", 4: "hell"}
    for lvl in range(1, 5):
        lvl_themes = {"perimeter": 0, "split": 0, "holes": 0, "chaos": 0}
        for i in range(PUZZLE_COUNT):
            if levels[i] == lvl:
                lvl_themes[themes[i]] += 1
        total_lvl = sum(lvl_themes.values())
        pcts = {k: f"{v / total_lvl * 100:.1f}%" for k, v in lvl_themes.items()}
        print(f"  {level_names[lvl]:>6}: {lvl_themes} ({pcts})")

    # Step 2: Solution counting (slow, use multiprocessing)
    print("Step 2/3: Solution counting (multiprocessing)...")
    solutions = [0] * PUZZLE_COUNT

    # Split into chunks for multiprocessing
    num_workers = min(multiprocessing.cpu_count(), 8)
    chunk_size = 50
    all_indices = list(range(PUZZLE_COUNT))
    chunks = [all_indices[i:i + chunk_size] for i in range(0, len(all_indices), chunk_size)]

    completed = 0
    with multiprocessing.Pool(num_workers) as pool:
        for batch_results in pool.imap_unordered(analyze_batch, chunks):
            for idx, count in batch_results:
                solutions[idx] = count
            completed += len(batch_results)
            if completed % 500 == 0 or completed == PUZZLE_COUNT:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (PUZZLE_COUNT - completed) / rate if rate > 0 else 0
                print(f"  {completed}/{PUZZLE_COUNT} solved ({rate:.0f}/s, ETA {eta:.0f}s)")

    # Verify all solutions >= 1
    zero_solutions = sum(1 for s in solutions if s == 0)
    if zero_solutions:
        print(f"  WARNING: {zero_solutions} puzzles have 0 solutions!")
    print(f"  Solution distribution: min={min(solutions)}, max={max(solutions)}, "
          f"median={sorted(solutions)[PUZZLE_COUNT // 2]}")
    single_solution = sum(1 for s in solutions if s == 1)
    print(f"  Single-solution puzzles: {single_solution} ({single_solution / PUZZLE_COUNT * 100:.1f}%)")

    # Step 3: Pocket analysis (Hell only)
    print("Step 3/3: Pocket analysis (Hell level)...")
    pocket_scores = [0] * PUZZLE_COUNT
    hell_count = 0
    for i in range(PUZZLE_COUNT):
        if levels[i] == 4:  # Hell
            grey_cells = decode_puzzle_cells(i)
            pocket_scores[i] = compute_pocket_score(grey_cells)
            hell_count += 1
    print(f"  Analyzed {hell_count} Hell puzzles")
    hell_pockets = [pocket_scores[i] for i in range(PUZZLE_COUNT) if levels[i] == 4]
    if hell_pockets:
        print(f"  Pocket scores: min={min(hell_pockets)}, max={max(hell_pockets)}, "
              f"avg={sum(hell_pockets) / len(hell_pockets):.2f}")

    # Output
    output = {
        "version": "2026-04-08",
        "total": PUZZLE_COUNT,
        "themes": themes,
        "solutions": solutions,
        "pocket_scores": pocket_scores,
    }

    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "puzzle_analysis.json")
    with open(output_path, "w") as f:
        json.dump(output, f)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s. Output: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
