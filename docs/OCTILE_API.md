# Octile Scoreboard API

Scoreboard API for the Octile puzzle game. Stores scores in a separate SQLite database (`octile.db`), isolated from the main XSW cache and analytics databases.

## Anti-Cheat Layers

| Layer | What | Effect |
|-------|------|--------|
| **Version check** | Optional `data_version` field on score submit | Rejects outdated clients with 409 (opt-in) |
| **Validation** | Puzzle range 1–91024, time 10s–24h | Rejects obviously invalid submissions |
| **Solution verification** | Server verifies board state against puzzle data | Cheaters cannot submit without actually solving the puzzle |
| **Rate limiting** | 1 submission per UUID per 30 seconds | Prevents spam/flooding |
| **Anomaly detection** | Flags >50 solves/hr or avg <20s over 10+ solves | Marks suspicious accounts for review (doesn't reject) |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/octile/version` | Puzzle data version info (for client compat checks) |
| POST | `/octile/score` | Submit a score |
| GET | `/octile/scoreboard` | Get scoreboard |
| GET | `/octile/leaderboard` | EXP-based leaderboard |
| GET | `/octile/puzzles` | List puzzles with stats |
| GET | `/octile/puzzle/{number}` | Get decoded puzzle cells |
| GET | `/octile/levels` | Puzzle counts per difficulty |
| GET | `/octile/level/{level}/puzzle/{slot}` | Get puzzle by difficulty + slot |
| POST | `/octile/auth/register` | Register (sends OTP email) |
| POST | `/octile/auth/verify` | Verify email with OTP |
| POST | `/octile/auth/login` | Login with email/password |
| POST | `/octile/auth/forgot-password` | Send password reset OTP |
| POST | `/octile/auth/reset-password` | Reset password with OTP |
| GET | `/octile/auth/me` | Get current user profile |
| GET | `/octile/auth/google` | Google OAuth redirect |
| GET | `/octile/auth/google/callback` | Google OAuth callback |
| POST | `/octile/auth/google/verify` | Google ID token verify (Android) |
| POST | `/octile/sync/push` | Push progress to server |
| GET | `/octile/sync/pull` | Pull progress from server |
| GET | `/octile/player/{uuid}/stats` | Player stats |
| GET | `/octile/player/{uuid}/elo` | Player ELO rating |
| GET | `/octile/analytics` | User distribution data (JSON) |
| GET | `/octile/analytics/dashboard` | Analytics dashboard (HTML) |
| POST | `/octile/feedback` | Submit feedback |

---

### GET `/octile/version`

Returns puzzle data version info. Clients should check this on startup to detect incompatible updates.

**Response** (200 OK):

```json
{
  "data_version": "2026-04-02",
  "data_hash": "a1b2c3d4e5f67890",
  "puzzle_count": 11378,
  "total_puzzles": 91024,
  "encoding": "base92-3char",
  "solution_formats": ["8-char-compact", "27-char-compact", "128-char-legacy"]
}
```

| Field | Description |
|-------|-------------|
| `data_version` | Date string, bumped when puzzle data changes |
| `data_hash` | SHA-256 prefix of puzzle data (16 hex chars) |
| `puzzle_count` | Base puzzles (before D4 transforms) |
| `total_puzzles` | Total including 8 D4 transforms per base |
| `encoding` | Puzzle data encoding format |
| `solution_formats` | Accepted solution string formats |

**Client usage:**

```javascript
const ver = await fetch('/octile/version').then(r => r.json());
if (ver.data_hash !== localPuzzleHash) {
  // Prompt user to refresh/update
}
```

---

### POST `/octile/score`

Submit a puzzle solve score.

**Request body** (JSON):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `puzzle_number` | int | Yes | Puzzle identifier (1–91024) |
| `resolve_time` | float | Yes | Solve time in seconds (10–86400) |
| `browser_uuid` | string | Yes | Persistent browser UUID identifying the player |
| `solution` | string | No* | Board state (8-char, 27-char, or 128-char format) |
| `data_version` | string | No | Client puzzle data version (for compat check) |
| `timestamp_utc` | string | No | Legacy: ignored, server uses `created_at` |
| `os` | string | No | Legacy: ignored |
| `browser` | string | No | Legacy: ignored |

\* `solution` is currently optional for backward compatibility.

**Solution formats** (all accepted):

| Format | Length | Description |
|--------|--------|-------------|
| 8-char compact | 8 | Base-92 encoded full board (newest) |
| 27-char compact | 27 | Base-92 encoded non-grey cells only |
| 128-char legacy | 128 | 64 × 2-char piece IDs |

**Version compatibility** (returns 409 if `data_version` is sent and mismatched):

```json
{
  "detail": "puzzle data outdated, please refresh",
  "current_version": "2026-04-02",
  "data_hash": "a1b2c3d4e5f67890"
}
```

Old clients that don't send `data_version` are unaffected (field is optional, defaults to null, check is skipped).

**Validation rules** (returns 400):
- `puzzle_number` must be 1–91024
- `resolve_time` must be 10–86400 seconds
- If `solution` is provided: must be valid for the given puzzle

**Rate limiting** (returns 429):
- Max 1 submission per `browser_uuid` per 30 seconds

**Anomaly flagging** (score accepted but `flagged=1`):
- More than 50 scores from the same UUID in the last hour
- Average solve time < 20 seconds across 10+ solves

**Server-calculated fields** (authoritative, not client-provided):
- `exp` — EXP reward based on difficulty and solve time
- `diamonds` — 1 per solve (0 if flagged)
- `grade` — S (≤par), A (≤2×par), B (normal)
- `elo` — ELO change for the player

**Response** (201 Created):

```json
{
  "id": 1,
  "puzzle_number": 1,
  "resolve_time": 45.2,
  "browser_uuid": "550e8400-...",
  "created_at": "2026-04-02T12:00:01.234567",
  "flagged": 0,
  "exp": 150,
  "diamonds": 1,
  "grade": "A",
  "elo": 1225.3
}
```

---

### GET `/octile/scoreboard`

Retrieve the scoreboard. By default returns the **best (fastest) score per player per puzzle** (leaderboard mode).

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `puzzle` | int | — | Filter by puzzle number |
| `uuid` | string | — | Filter by browser UUID |
| `best` | bool | `true` | `true` = one best per player per puzzle; `false` = all |
| `limit` | int | 50 | Max results (1–200) |
| `offset` | int | 0 | Pagination offset |

---

### GET `/octile/leaderboard`

EXP-based global leaderboard. Returns players ranked by total server-verified EXP. Merges scores across multiple browser UUIDs for authenticated users.

**Query parameters**: `limit` (int, default 50, max 200)

---

### GET `/octile/puzzle/{number}`

Get decoded puzzle cells for a given puzzle number (1-based, up to 91024).

**Response** (200 OK):

```json
{
  "puzzle_number": 42,
  "base_puzzle": 42,
  "transform": 0,
  "cells": [0, 9, 10, 32, 40, 48],
  "difficulty": 2,
  "difficulty_label": "medium"
}
```

---

### GET `/octile/levels`

Puzzle counts per difficulty level.

**Query parameters**: `transforms` (int, default 8, 1=base only)

**Response**: `{"easy": 2848, "medium": 4552, "hard": 2832, "hell": 1146}`

---

## Authentication

Two-step email/password registration with OTP verification. Also supports Google OAuth.

### Registration flow

1. `POST /octile/auth/register` — sends 6-digit OTP to email
2. `POST /octile/auth/verify` — verify OTP, returns JWT

### Login

- `POST /octile/auth/login` — email + password, returns JWT
- `GET /octile/auth/google` — redirects to Google consent screen
- `POST /octile/auth/google/verify` — Android ID token flow

### Progress sync

- `POST /octile/sync/push` — push local progress (MAX merge strategy)
- `GET /octile/sync/pull` — pull server progress

JWT is passed as `Authorization: Bearer <token>`.

---

## Database

Scores are stored in `octile.db` (configurable via `OCTILE_DB_PATH`).

**Tables**: `octile_scores`, `octile_users`, `octile_progress`

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OCTILE_DB_PATH` | `octile.db` | SQLite database path |
| `OCTILE_SMTP_HOST` | — | SMTP host for OTP/backup emails |
| `OCTILE_SMTP_USER` | — | SMTP username |
| `OCTILE_SMTP_PASSWORD` | — | SMTP password |
| `OCTILE_SMTP_PORT` | `587` | SMTP port |
| `OCTILE_FROM_EMAIL` | smtp_user | From address |
| `OCTILE_GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `OCTILE_GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `OCTILE_JWT_SECRET` | random | JWT signing secret |
| `OCTILE_SITE_URL` | — | Redirect URL after Google OAuth |
| `WORKER_HMAC_SECRET` | — | Shared secret for Worker HMAC signing |

## Backup

```bash
# Full backup (SQLite copy + JSON dump)
python3 scripts/backup_octile.py

# Backup + email to octileapp@googlegroups.com
python3 scripts/backup_octile.py --email
```

## Deployment

The version endpoint enables safe rolling updates:

1. **Deploy server** with new puzzle data
2. **Bump `OCTILE_DATA_VERSION`** in octile_api.py
3. **Update client** to send `data_version` on score submit
4. Server rejects outdated clients with 409 + `current_version`
5. Client prompts user to refresh

Old clients without `data_version` field are never rejected (backward compatible).
