# Octile Scoreboard API

Scoreboard API for the Octile puzzle game. Stores scores in a separate SQLite database (`octile.db`), isolated from the main XSW cache and analytics databases.

## Anti-Cheat Layers

| Layer | What | Effect |
|-------|------|--------|
| **Validation** | Puzzle range 1–11378, time 10s–24h | Rejects obviously invalid submissions |
| **Solution verification** | Server verifies 128-char board state against puzzle data | Cheaters cannot submit without actually solving the puzzle |
| **Rate limiting** | 1 submission per UUID per 30 seconds | Prevents spam/flooding |
| **Anomaly detection** | Flags >50 solves/hr or avg <20s over 10+ solves | Marks suspicious accounts for review (doesn't reject) |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/octile/score` | Submit a score |
| GET | `/octile/scoreboard` | Get scoreboard |
| GET | `/octile/puzzles` | List puzzles with stats |

---

### POST `/octile/score`

Submit a puzzle solve score.

**Request body** (JSON):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `puzzle_number` | int | Yes | Puzzle identifier (1–11378) |
| `resolve_time` | float | Yes | Solve time in seconds (10–86400) |
| `browser_uuid` | string | Yes | Persistent browser UUID identifying the player |
| `solution` | string | No* | 128-char compact board state (64 cells × 2-char piece ID) |
| `timestamp_utc` | string | No | Legacy: ISO 8601 UTC timestamp (accepted but ignored; server uses `created_at`) |
| `os` | string | No | Legacy: client-detected OS (accepted but ignored; server parses User-Agent) |
| `browser` | string | No | Legacy: client-detected browser (accepted but ignored) |

\* `solution` is currently optional for backward compatibility. Will become required once all clients are updated.

**Solution encoding**: A 128-character string representing the 8×8 board, left-to-right, top-to-bottom. Each cell is a 2-char piece ID:

| Piece ID | Piece | Cells | Valid sizes |
|----------|-------|-------|-------------|
| `g1` | grey1 | 1 | 1×1 |
| `g2` | grey2 | 2 | 1×2, 2×1 |
| `g3` | grey3 | 3 | 1×3, 3×1 |
| `r1` | red1 | 6 | 2×3, 3×2 |
| `r2` | red2 | 4 | 1×4, 4×1 |
| `w1` | white1 | 5 | 1×5, 5×1 |
| `w2` | white2 | 4 | 2×2 |
| `b1` | blue1 | 10 | 2×5, 5×2 |
| `b2` | blue2 | 12 | 3×4, 4×3 |
| `y1` | yel1 | 9 | 3×3 |
| `y2` | yel2 | 8 | 2×4, 4×2 |

The server automatically extracts from request headers:
- `client_ip` — from `X-Forwarded-For` (first entry) or `request.client.host`
- `client_host` — `Host` header
- `user_agent` — `User-Agent` header (used to detect OS/browser)
- `forwarded_for` — full `X-Forwarded-For` header
- `origin` — `Origin` header
- `real_ip` — `X-Real-IP` header

**Validation rules** (returns 400):
- `puzzle_number` must be 1–11378
- `resolve_time` must be ≥ 10 seconds (impossible to solve faster)
- `resolve_time` must be ≤ 86400 seconds (24 hours)
- If `solution` is provided: must be a valid solved board for the given puzzle

**Rate limiting** (returns 429):
- Max 1 submission per `browser_uuid` per 30 seconds

**Anomaly flagging** (score accepted but `flagged=1`):
- More than 50 scores from the same UUID in the last hour
- Average solve time < 20 seconds across 10+ solves

**Response** (201 Created):

```json
{
  "id": 1,
  "puzzle_number": 1,
  "resolve_time": 12.345,
  "browser_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-18T12:00:01.234567",
  "timestamp_utc": "2026-03-18T12:00:01.234567",
  "flagged": 0
}
```

Note: `timestamp_utc` in the response is an alias for `created_at` (for backward compatibility with old clients).

**Example**:

```bash
curl -X POST http://localhost:8000/octile/score \
  -H "Content-Type: application/json" \
  -d '{
    "puzzle_number": 1,
    "resolve_time": 12.345,
    "browser_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "solution": "g1g2g2g3g3g3b1b1b2b2b2b2y2y2b1b1b2b2b2b2y2y2b1b1b2b2b2b2y2y2b1b1r2y1y1y1y2y2b1b1r2y1y1y1w2w2r1r1r2y1y1y1w2w2r1r1r2w1w1w1w1w1r1r1"
  }'
```

**Error examples**:

```bash
# Puzzle number out of range → 400
curl -X POST ... -d '{"puzzle_number": 0, ...}'

# Too fast → 400
curl -X POST ... -d '{"resolve_time": 5, ...}'

# Invalid solution → 400
curl -X POST ... -d '{"solution": "xxxxxxxxxxxx...", ...}'

# Rate limited → 429 (submitted again within 30s)
```

---

### GET `/octile/scoreboard`

Retrieve the scoreboard. By default returns the **best (fastest) score per player per puzzle** (leaderboard mode).

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `puzzle` | int | — | Filter by puzzle number |
| `uuid` | string | — | Filter by browser UUID |
| `best` | bool | `true` | `true` = one best score per player per puzzle; `false` = all scores |
| `limit` | int | 50 | Max results (1–200) |
| `offset` | int | 0 | Pagination offset |

**Response** (200 OK):

```json
{
  "puzzle_number": 1,
  "total": 3,
  "scores": [
    {
      "id": 2,
      "puzzle_number": 1,
      "resolve_time": 8.5,
      "browser_uuid": "uuid-alice",
      "created_at": "2026-03-18T12:01:01",
      "timestamp_utc": "2026-03-18T12:01:01",
      "flagged": 0
    },
    {
      "id": 1,
      "puzzle_number": 1,
      "resolve_time": 12.345,
      "browser_uuid": "uuid-bob",
      "created_at": "2026-03-18T12:00:01",
      "timestamp_utc": "2026-03-18T12:00:01",
      "flagged": 0
    }
  ]
}
```

Scores are always ordered by `resolve_time ASC` (fastest first).

**Examples**:

```bash
# Leaderboard for puzzle 1
curl "http://localhost:8000/octile/scoreboard?puzzle=1"

# All attempts by a specific player
curl "http://localhost:8000/octile/scoreboard?uuid=550e8400-e29b-41d4-a716-446655440000&best=false"

# Top 10 across all puzzles
curl "http://localhost:8000/octile/scoreboard?limit=10"

# Page 2 (scores 11-20)
curl "http://localhost:8000/octile/scoreboard?limit=10&offset=10"
```

---

### GET `/octile/puzzles`

List all puzzles that have at least one score, with aggregate stats.

**Response** (200 OK):

```json
[
  {
    "puzzle_number": 1,
    "total_scores": 42,
    "unique_players": 15,
    "best_time": 8.5
  },
  {
    "puzzle_number": 2,
    "total_scores": 28,
    "unique_players": 12,
    "best_time": 11.2
  }
]
```

Ordered by `puzzle_number ASC`. Returns an empty array `[]` if no scores exist.

**Example**:

```bash
curl http://localhost:8000/octile/puzzles
```

---

## Database

Scores are stored in `octile.db` (configurable via `OCTILE_DB_PATH` env var), separate from the main application database.

**Table: `octile_scores`**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `puzzle_number` | INTEGER | Puzzle identifier (1–11378) |
| `resolve_time` | FLOAT | Solve time in seconds |
| `browser_uuid` | VARCHAR | Player browser UUID |
| `timestamp_utc` | DATETIME | Legacy: client-provided timestamp (nullable for new clients) |
| `client_ip` | VARCHAR | Resolved client IP |
| `client_host` | VARCHAR | Host header |
| `user_agent` | VARCHAR | User-Agent header (source for OS/browser detection) |
| `forwarded_for` | VARCHAR | X-Forwarded-For header |
| `origin` | VARCHAR | Origin header |
| `real_ip` | VARCHAR | X-Real-IP header |
| `os` | VARCHAR | Legacy: client-provided OS (nullable) |
| `browser` | VARCHAR | Legacy: client-provided browser (nullable) |
| `solution` | VARCHAR | 128-char board state for audit |
| `flagged` | INTEGER | 0=normal, 1=flagged for review |
| `created_at` | DATETIME | Server-side insertion time |

**Indexes**: `puzzle_number`, `browser_uuid`, `(puzzle_number, resolve_time)`, `(browser_uuid, puzzle_number)`, `(browser_uuid, created_at)`, `created_at`

**Migration**: New columns (`solution`, `flagged`) are added automatically via `ALTER TABLE` on startup if missing.

## Files

| File | Description |
|------|-------------|
| `octile_api.py` | API endpoints, validation, verification, DB model |
| `octile_puzzle_data.py` | 11,378 puzzles encoded as base64 string (68KB) |
| `tests/test_octile_api.py` | 30 tests covering all endpoints and anti-cheat layers |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OCTILE_DB_PATH` | `octile.db` | Path to the Octile SQLite database file |

## Deployment

The anti-cheat changes are backward compatible. Recommended deployment order:

1. **Deploy server** — accepts both old format (no solution) and new format (with solution)
2. **Deploy client** — sends solution + legacy `timestamp_utc` for compat with old server
3. **Make solution required** — once all clients are updated, make `solution` non-optional
