# Puzzle Ordering v2: Themed Chapters with Difficulty Curves

## Overview

v2 replaces the v1 monotonic difficulty ramp with themed chapters and
step-ladder difficulty curves. Each chapter feels like a mini-journey
(intro -> grind -> peak -> cooldown), and chapters progress through
geometric themes.

**Key constraint:** Backend-only change. The client requests `(level, slot)`
and gets back a puzzle. The ordering is determined by the `"ordering"` field
in `difficulty_levels.json`, read by `_get_level_bases()`.

## Architecture

```
puzzle_analysis.json     (one-time analysis output)
        |
        v
reorder_puzzles.py       (generates ordering)
        |
        v
difficulty_levels.json   (adds "ordering" + "ordering_version" fields)
        |
        v
octile_api.py            (_get_level_bases reads ordering if present)
```

## Theme Classification

Each puzzle's 6 grey cells are classified into a geometric theme:

| Theme | Rule | Player experience |
|-------|------|-------------------|
| **Perimeter** | >= 5 of 6 grey cells on board edge | Easy to visualize center |
| **Split** | Grey cells disconnect free space, or all on same row/col | Board feels like two sub-puzzles |
| **Holes** | All 3 grey pieces mutually non-adjacent | Scattered obstacles |
| **Chaos** | Everything else | No pattern to exploit |

**Split was merged into Holes** because split had only 69 puzzles (0.6%)
across all levels -- too small for dedicated chapters.

### Distribution (11,378 puzzles)

| Theme | Count | % |
|-------|-------|---|
| Perimeter | 1,722 | 15.1% |
| Holes (+split) | 6,140 | 54.0% |
| Chaos | 3,516 | 30.9% |

## Composite Difficulty Score

```
score = 0.7 * attempts_normalized + 0.3 * (1 - solutions_normalized)
```

- `attempts_normalized`: min-max within level (0=easiest, 1=hardest)
- `solutions_normalized`: min-max within level (0=fewest, 1=most solutions)
- Fewer solutions + more attempts = harder
- Hell bonus: `+0.1 * min(pocket_score, 2)` (all pockets scored 1, so uniform)

## Level Ordering

Within each level: **perimeter -> holes -> chaos**

Within each theme, puzzles are sorted by composite difficulty score,
then split into chapters with step-ladder reordering.

| Level | Puzzles | Chapter size | Perimeter ch. | Holes ch. | Chaos ch. |
|-------|---------|-------------|--------------|----------|----------|
| Easy | 2,876 | 100 | 4 | 17 | 9 |
| Medium | 2,815 | 100 | 4 | 16 | 10 |
| Hard | 3,981 | 125 | 5 | 18 | 10 |
| Hell | 1,706 | 65 | 6 | 12 | 9 |

## Step-Ladder Curve

Each chapter of N puzzles (sorted by difficulty):

| Zone | Slots | Source | Experience |
|------|-------|--------|------------|
| Introduction | 1-20% | Easiest 20% | "I can do this" |
| The Grind | 21-80% | Next 60% (ascending) | Progressive challenge |
| The Peak | 81-95% | Top 5% (hardest) | "This is tough" |
| Cool Down | 96-100% | 80-95th percentile | "Satisfying finish" |

## Data Format

`difficulty_levels.json` adds two fields:

```json
{
  "ordering": {
    "1": [4572, 8821, 102, ...],
    "2": [33, 1205, ...],
    "3": [2, 5, 6, ...],
    "4": [35, 36, 49, ...]
  },
  "ordering_version": "2026-04-08"
}
```

Each array = base puzzle indices in display order for that level.

## Version Switching

Controlled by `OCTILE_ORDERING` env var (default: `v2`):

| Version | Env value | Behavior |
|---------|-----------|----------|
| v0 | `OCTILE_ORDERING=v0` | Raw puzzle index order (no sorting) |
| v1 | `OCTILE_ORDERING=v1` | Sort by solver attempts ascending |
| v2 | `OCTILE_ORDERING=v2` (default) | Themed chapters + step-ladder curves |

Switch at deploy time:
```bash
# Use v1 ordering
OCTILE_ORDERING=v1 uvicorn main:app

# Use v2 (default, same as not setting it)
OCTILE_ORDERING=v2 uvicorn main:app

# Docker
docker run -e OCTILE_ORDERING=v1 ...
```

A/B testing: run two backend instances with different env vars behind
a load balancer that routes by player ID or cookie. See below.

No client changes needed. No API contract changes. The cache
(`_LEVEL_BASES`) is set once at startup per process.

## Player Progress Impact

Progress stored as `octile_level_easy = 47` (slot count). After reordering,
slot 47 maps to a different puzzle. The player won't lose progress count --
they just see a new puzzle at their current position. One-time shift.

## Scripts

- `scripts/analyze_puzzles.py` -- one-time analysis (themes, solution count,
  pockets). Outputs `puzzle_analysis.json`. Runtime ~45s with multiprocessing.
- `scripts/reorder_puzzles.py` -- reads analysis + difficulty data, outputs
  updated `difficulty_levels.json` with ordering.

## Solution Count Stats

- Min: 1, Max: 100 (capped), Median: 5
- Single-solution puzzles: 1,688 (14.8%)
- Solution count correlates with difficulty: harder puzzles tend to have
  fewer solutions

## TODO

- [ ] A/B testing: per-request ordering version selection (query param or
  cookie-based routing) so v1 vs v2 can be compared on the same backend
  instance. Options: (a) backend reads `?ordering=v1` param, worker injects
  based on player UUID hash; (b) two backend containers with different
  `OCTILE_ORDERING`, worker routes by UUID.

## Verification

Run tests:
```bash
pytest tests/test_octile_api.py -k "level_slot or level_ordering or level_puzzle_sequential"
```

Key tests:
- `test_level_ordering_integrity` -- correct count, no duplicates, correct level membership
- `test_level_slot_ordering` -- first slot easier than last slot
- `test_get_level_puzzle_sequential_order` -- same via API
