#!/usr/bin/env python3
"""
Classify all 11,378 Octile puzzles into difficulty levels by solver backtrack count.

Instruments the backtracking solver to count the total number of placement
attempts. Puzzles requiring more attempts = harder.

Output: difficulty_levels.json mapping puzzle index to level (1-4).
"""

import json
import time
from multiprocessing import Pool, cpu_count

N = 8
FULL = (1 << 64) - 1

# Pieces sorted largest first (same order as the solver)
PLAYER_PIECES = [
    (3, 4),   # blue2: 12 cells
    (2, 5),   # blue1: 10 cells
    (3, 3),   # yel1:  9 cells
    (2, 4),   # yel2:  8 cells
    (2, 3),   # red1:  6 cells
    (1, 5),   # white1: 5 cells
    (1, 4),   # red2:  4 cells
    (2, 2),   # white2: 4 cells
]


def precompute_placements():
    result = []
    for rows, cols in PLAYER_PIECES:
        orientations = {(rows, cols)}
        if rows != cols:
            orientations.add((cols, rows))
        by_cell = [[] for _ in range(64)]
        for rr, cc in orientations:
            for sr in range(N - rr + 1):
                for sc in range(N - cc + 1):
                    mask = 0
                    cells = []
                    for dr in range(rr):
                        for dc in range(cc):
                            bit = (sr + dr) * N + (sc + dc)
                            mask |= 1 << bit
                            cells.append(bit)
                    for bit in cells:
                        by_cell[bit].append(mask)
        result.append(by_cell)
    return result


PIECE_BY_CELL = precompute_placements()


def solve_count_attempts(grey_mask):
    """Solve and return the number of placement attempts (backtracks)."""
    board = [grey_mask]
    pieces_used = [0]
    attempts = [0]

    def backtrack(depth):
        if depth == 8:
            return board[0] == FULL

        remaining = FULL & ~board[0]
        if not remaining:
            return False
        cell = (remaining & -remaining).bit_length() - 1

        brd = board[0]
        pu = pieces_used[0]

        for pi in range(8):
            if pu & (1 << pi):
                continue
            for mask in PIECE_BY_CELL[pi][cell]:
                if mask & brd == 0:
                    attempts[0] += 1
                    board[0] = brd | mask
                    pieces_used[0] = pu | (1 << pi)
                    if backtrack(depth + 1):
                        return True

            board[0] = brd
            pieces_used[0] = pu

        return False

    backtrack(0)
    return attempts[0]


# Base-92 decoding (matches octile_api.py)
P92 = '!"#$%&()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{|}~'
P92_MAP = {c: i for i, c in enumerate(P92)}


def load_puzzle_data():
    """Load puzzle data from octile_puzzle_data.py in xsw repo."""
    import sys
    sys.path.insert(0, '/Users/oouyang/ws/xsw')
    from octile_puzzle_data import PUZZLE_DATA
    return PUZZLE_DATA


def decode_puzzle(data, index):
    """Decode puzzle at 0-based index, return grey cell bitmask."""
    o = index * 3
    n = P92_MAP[data[o]] + P92_MAP[data[o + 1]] * 92 + P92_MAP[data[o + 2]] * 92 * 92

    g3_idx = n % 96
    g2_idx = (n // 96) % 112
    g1 = n // 10752

    mask = 1 << g1

    if g2_idx < 56:
        r, c = divmod(g2_idx, 7)
        a = r * 8 + c
        mask |= (1 << a) | (1 << (a + 1))
    else:
        i = g2_idx - 56
        r, c = divmod(i, 8)
        a = r * 8 + c
        mask |= (1 << a) | (1 << (a + 8))

    if g3_idx < 48:
        r, c = divmod(g3_idx, 6)
        a = r * 8 + c
        mask |= (1 << a) | (1 << (a + 1)) | (1 << (a + 2))
    else:
        i = g3_idx - 48
        r, c = divmod(i, 8)
        a = r * 8 + c
        mask |= (1 << a) | (1 << (a + 8)) | (1 << (a + 16))

    return mask


def process_batch(args):
    """Process a batch of puzzles, return list of (index, attempts)."""
    data, indices = args
    results = []
    for idx in indices:
        grey_mask = decode_puzzle(data, idx)
        attempts = solve_count_attempts(grey_mask)
        results.append((idx, attempts))
    return results


def main():
    print("Loading puzzle data...")
    data = load_puzzle_data()
    total = len(data) // 3
    print(f"Loaded {total} puzzles")

    print(f"Classifying puzzles using {cpu_count()} CPU cores...")
    t0 = time.time()

    # Create batches
    batch_size = max(1, total // (cpu_count() * 4))
    all_indices = list(range(total))
    batches = [(data, all_indices[i:i + batch_size])
               for i in range(0, total, batch_size)]

    # Process in parallel
    attempts_map = {}
    done = 0
    with Pool(cpu_count()) as pool:
        for results in pool.imap_unordered(process_batch, batches):
            for idx, attempts in results:
                attempts_map[idx] = attempts
            done += len(results)
            if done % 2000 < batch_size or done == total:
                elapsed = time.time() - t0
                print(f"  {done}/{total} ({done*100/total:.0f}%) — {elapsed:.0f}s")

    t1 = time.time()
    print(f"\nDone in {t1 - t0:.1f}s")

    # Analyze distribution
    all_attempts = sorted(attempts_map.values())
    print(f"\nAttempt distribution:")
    print(f"  Min: {all_attempts[0]}")
    print(f"  25th percentile: {all_attempts[len(all_attempts) // 4]}")
    print(f"  Median: {all_attempts[len(all_attempts) // 2]}")
    print(f"  75th percentile: {all_attempts[3 * len(all_attempts) // 4]}")
    print(f"  90th percentile: {all_attempts[9 * len(all_attempts) // 10]}")
    print(f"  95th percentile: {all_attempts[95 * len(all_attempts) // 100]}")
    print(f"  Max: {all_attempts[-1]}")

    # Classify into 4 levels using percentiles
    p25 = all_attempts[len(all_attempts) // 4]
    p50 = all_attempts[len(all_attempts) // 2]
    p85 = all_attempts[85 * len(all_attempts) // 100]

    levels = {}
    level_counts = [0, 0, 0, 0]
    for idx, att in attempts_map.items():
        if att <= p25:
            level = 1  # easy
        elif att <= p50:
            level = 2  # medium
        elif att <= p85:
            level = 3  # hard
        else:
            level = 4  # hell
        levels[idx] = level
        level_counts[level - 1] += 1

    print(f"\nLevel distribution:")
    print(f"  Easy (1):   {level_counts[0]} ({level_counts[0]*100/total:.1f}%)")
    print(f"  Medium (2): {level_counts[1]} ({level_counts[1]*100/total:.1f}%)")
    print(f"  Hard (3):   {level_counts[2]} ({level_counts[2]*100/total:.1f}%)")
    print(f"  Hell (4):   {level_counts[3]} ({level_counts[3]*100/total:.1f}%)")
    print(f"\nThresholds: easy ≤{p25}, medium ≤{p50}, hard ≤{p85}, hell >{p85}")

    # Save results
    output = {
        "total": total,
        "thresholds": {"easy": p25, "medium": p50, "hard": p85},
        "distribution": {
            "easy": level_counts[0],
            "medium": level_counts[1],
            "hard": level_counts[2],
            "hell": level_counts[3],
        },
        "stats": {
            "min": all_attempts[0],
            "p25": p25,
            "median": all_attempts[len(all_attempts) // 2],
            "p75": all_attempts[3 * len(all_attempts) // 4],
            "p85": p85,
            "p90": all_attempts[9 * len(all_attempts) // 10],
            "p95": all_attempts[95 * len(all_attempts) // 100],
            "max": all_attempts[-1],
        },
        # levels[i] = 1-4 for puzzle index i (0-based)
        "levels": [levels[i] for i in range(total)],
    }

    with open("difficulty_levels.json", "w") as f:
        json.dump(output, f)
    print(f"\nSaved to difficulty_levels.json")


if __name__ == "__main__":
    main()
