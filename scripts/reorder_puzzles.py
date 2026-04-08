#!/usr/bin/env python3
"""
Puzzle reordering script for Octile v2.

Reads difficulty_levels.json + puzzle_analysis.json, outputs updated
difficulty_levels.json with new "ordering" field.

Ordering strategy:
  1. Within each level, puzzles are grouped by theme:
     perimeter -> split -> holes -> chaos
  2. Within each theme group, puzzles are sorted by composite difficulty score
  3. Each chapter applies a step-ladder curve:
     intro (20%) -> grind (60%) -> peak (15%) -> cooldown (5%)
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

# Split (69 puzzles total, <1%) is too small for its own section.
# Merge into holes (both involve disconnection/barriers).
THEME_ORDER = ["perimeter", "holes", "chaos"]
MERGE_THEMES = {"split": "holes"}  # split -> holes

CHAPTER_SIZES = {1: 100, 2: 100, 3: 125, 4: 65}

# Level names for display
LEVEL_NAMES = {1: "easy", 2: "medium", 3: "hard", 4: "hell"}


def compute_composite_score(attempts_norm, solutions_norm, pocket_score=0, is_hell=False):
    """Composite difficulty score: higher = harder."""
    score = 0.7 * attempts_norm + 0.3 * (1.0 - solutions_norm)
    if is_hell:
        score += 0.1 * min(pocket_score, 2)
    return score


def step_ladder_reorder(puzzles_sorted):
    """Apply step-ladder curve to a chapter of puzzles (already sorted by difficulty).

    Input: list of (base_idx, score) sorted by score ascending
    Output: reordered list of base_idx

    Zones:
      - Intro (first 20%): easiest puzzles
      - Grind (next 60%): progressive difficulty
      - Peak (next 15%): hardest puzzles
      - Cooldown (last 5%): slightly easier (from 80-95th percentile range)
    """
    n = len(puzzles_sorted)
    if n <= 4:
        return [idx for idx, _ in puzzles_sorted]

    # Split into percentile groups
    p20 = max(1, int(n * 0.20))
    p80 = max(p20 + 1, int(n * 0.80))
    p95 = max(p80 + 1, int(n * 0.95))

    intro = puzzles_sorted[:p20]
    grind = puzzles_sorted[p20:p80]
    peak = puzzles_sorted[p95:]       # top 5% = hardest
    cooldown = puzzles_sorted[p80:p95]  # 80-95th percentile

    # Assemble: intro -> grind -> peak -> cooldown
    result = []
    for idx, _ in intro:
        result.append(idx)
    for idx, _ in grind:
        result.append(idx)
    for idx, _ in peak:
        result.append(idx)
    for idx, _ in cooldown:
        result.append(idx)

    return result


def main():
    # Load data
    diff_path = os.path.join(BASE_DIR, "difficulty_levels.json")
    analysis_path = os.path.join(BASE_DIR, "puzzle_analysis.json")

    with open(diff_path) as f:
        diff_data = json.load(f)
    with open(analysis_path) as f:
        analysis = json.load(f)

    levels = diff_data["levels"]
    attempts = diff_data["attempts"]
    themes = analysis["themes"]
    solutions = analysis["solutions"]
    pocket_scores = analysis["pocket_scores"]
    total = diff_data["total"]

    assert len(levels) == total
    assert len(themes) == total
    assert len(solutions) == total

    print(f"Loaded {total} puzzles")

    ordering = {}

    for level in range(1, 5):
        level_name = LEVEL_NAMES[level]
        chapter_size = CHAPTER_SIZES[level]
        is_hell = (level == 4)

        # Collect puzzles for this level
        level_puzzles = []
        for i in range(total):
            if levels[i] == level:
                level_puzzles.append(i)

        # Compute normalized scores within level
        level_attempts = [attempts[i] for i in level_puzzles]
        level_solutions = [solutions[i] for i in level_puzzles]

        att_min, att_max = min(level_attempts), max(level_attempts)
        sol_min, sol_max = min(level_solutions), max(level_solutions)

        att_range = max(att_max - att_min, 1)
        sol_range = max(sol_max - sol_min, 1)

        # Compute composite scores
        scored = []
        for i in level_puzzles:
            att_norm = (attempts[i] - att_min) / att_range
            sol_norm = (solutions[i] - sol_min) / sol_range
            score = compute_composite_score(att_norm, sol_norm,
                                            pocket_scores[i], is_hell)
            scored.append((i, score, themes[i]))

        # Group by theme (with merging)
        by_theme = {t: [] for t in THEME_ORDER}
        for idx, score, theme in scored:
            effective_theme = MERGE_THEMES.get(theme, theme)
            by_theme[effective_theme].append((idx, score))

        # Sort each theme group by score
        for theme in THEME_ORDER:
            by_theme[theme].sort(key=lambda x: x[1])

        # Build final ordering: theme groups in order, each with step-ladder
        level_order = []
        theme_stats = {}

        for theme in THEME_ORDER:
            theme_puzzles = by_theme[theme]
            theme_stats[theme] = len(theme_puzzles)

            if not theme_puzzles:
                continue

            # Split into chapters and apply step-ladder to each
            for ch_start in range(0, len(theme_puzzles), chapter_size):
                chapter = theme_puzzles[ch_start:ch_start + chapter_size]
                reordered = step_ladder_reorder(chapter)
                level_order.extend(reordered)

        ordering[str(level)] = level_order

        # Print stats
        print(f"\n{level_name.upper()} (level {level}): {len(level_order)} puzzles, "
              f"chapter_size={chapter_size}")
        for theme in THEME_ORDER:
            count = theme_stats[theme]
            chapters = (count + chapter_size - 1) // chapter_size if count > 0 else 0
            pct = count / len(level_order) * 100
            print(f"  {theme:>10}: {count:5d} puzzles ({pct:5.1f}%), {chapters} chapters")

        # Verify step-ladder: check first full chapter
        if len(level_order) >= chapter_size:
            ch = level_order[:chapter_size]
            p20 = max(1, int(chapter_size * 0.20))
            p80 = max(p20 + 1, int(chapter_size * 0.80))
            p95 = max(p80 + 1, int(chapter_size * 0.95))
            intro_avg = sum(attempts[i] for i in ch[:p20]) / p20
            grind_avg = sum(attempts[i] for i in ch[p20:p80]) / (p80 - p20)
            peak_avg = sum(attempts[i] for i in ch[p95:]) / max(len(ch) - p95, 1)
            cool_avg = sum(attempts[i] for i in ch[p80:p95]) / max(p95 - p80, 1)
            print(f"  Chapter 1 step-ladder: intro={intro_avg:.0f} < grind={grind_avg:.0f} "
                  f"< peak={peak_avg:.0f} > cooldown={cool_avg:.0f}")

    # Verify integrity
    print("\n--- Integrity checks ---")
    for level in range(1, 5):
        order = ordering[str(level)]
        expected = sum(1 for l in levels if l == level)
        assert len(order) == expected, f"Level {level}: {len(order)} != {expected}"
        assert len(set(order)) == len(order), f"Level {level}: duplicates found"
        for idx in order:
            assert levels[idx] == level, f"Puzzle {idx} is level {levels[idx]}, expected {level}"
        print(f"  Level {level} ({LEVEL_NAMES[level]}): {len(order)} puzzles, no duplicates, "
              f"all correct level")

    # Verify union
    all_ordered = set()
    for order in ordering.values():
        all_ordered.update(order)
    assert len(all_ordered) == total, f"Union {len(all_ordered)} != {total}"
    print(f"  All {total} puzzles accounted for")

    # Write updated difficulty_levels.json
    diff_data["ordering"] = ordering
    diff_data["ordering_version"] = "2026-04-08"

    with open(diff_path, "w") as f:
        json.dump(diff_data, f, separators=(",", ":"))

    print(f"\nUpdated {diff_path}")
    print(f"File size: {os.path.getsize(diff_path) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
