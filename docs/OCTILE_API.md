# Octile Scoreboard API

Scoreboard API for the Octile puzzle game. Stores scores in a separate SQLite database (`octile.db`), isolated from the main XSW cache and analytics databases.

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
| `puzzle_number` | int | Yes | Puzzle identifier |
| `resolve_time` | float | Yes | Solve time in seconds |
| `browser_uuid` | string | Yes | Persistent browser UUID identifying the player |
| `timestamp_utc` | string | Yes | ISO 8601 UTC timestamp of the solve (e.g. `2026-03-18T12:00:00Z`) |
| `os` | string | No | Client-detected OS (e.g. `Windows 11`, `iOS 18`) |
| `browser` | string | No | Client-detected browser (e.g. `Chrome 120`, `Safari 18`) |

The server automatically extracts from the request headers:
- `client_ip` — from `X-Forwarded-For` (first entry) or `request.client.host`
- `client_host` — `Host` header
- `user_agent` — `User-Agent` header
- `forwarded_for` — full `X-Forwarded-For` header
- `origin` — `Origin` header
- `real_ip` — `X-Real-IP` header

**Response** (201 Created):

```json
{
  "id": 1,
  "puzzle_number": 1,
  "resolve_time": 12.345,
  "browser_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp_utc": "2026-03-18T12:00:00+00:00",
  "os": "Windows 11",
  "browser": "Chrome 120",
  "created_at": "2026-03-18T12:00:01.234567+00:00"
}
```

**Example**:

```bash
curl -X POST http://localhost:8000/octile/score \
  -H "Content-Type: application/json" \
  -d '{
    "puzzle_number": 1,
    "resolve_time": 12.345,
    "browser_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp_utc": "2026-03-18T12:00:00Z",
    "os": "Windows 11",
    "browser": "Chrome 120"
  }'
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
      "timestamp_utc": "2026-03-18T12:01:00+00:00",
      "os": "macOS",
      "browser": "Safari 18",
      "created_at": "2026-03-18T12:01:01+00:00"
    },
    {
      "id": 1,
      "puzzle_number": 1,
      "resolve_time": 12.345,
      "browser_uuid": "uuid-bob",
      "timestamp_utc": "2026-03-18T12:00:00+00:00",
      "os": "Windows 11",
      "browser": "Chrome 120",
      "created_at": "2026-03-18T12:00:01+00:00"
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
| `puzzle_number` | INTEGER | Puzzle identifier |
| `resolve_time` | FLOAT | Solve time in seconds |
| `browser_uuid` | VARCHAR | Player browser UUID |
| `timestamp_utc` | DATETIME | Client-provided solve timestamp |
| `client_ip` | VARCHAR | Resolved client IP |
| `client_host` | VARCHAR | Host header |
| `user_agent` | VARCHAR | User-Agent header |
| `forwarded_for` | VARCHAR | X-Forwarded-For header |
| `origin` | VARCHAR | Origin header |
| `real_ip` | VARCHAR | X-Real-IP header |
| `os` | VARCHAR | Client-provided OS |
| `browser` | VARCHAR | Client-provided browser |
| `created_at` | DATETIME | Server-side insertion time |

**Indexes**: `puzzle_number`, `browser_uuid`, `(puzzle_number, resolve_time)`, `(browser_uuid, puzzle_number)`, `created_at`

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OCTILE_DB_PATH` | `octile.db` | Path to the Octile SQLite database file |
