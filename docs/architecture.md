# Octile Architecture

## System Topology

```
                          ┌─────────────────────────────────────┐
                          │            Clients                  │
                          │                                     │
                          │  Web (browser tab / PWA)            │
                          │  Android (WebView APK)              │
                          │  iOS (WKWebView)                    │
                          │  Steam (Electron + Steamworks)      │
                          └──────┬──────────┬──────────┬────────┘
                                 │          │          │
                    ┌────────────┘          │          └────────────┐
                    │                       │                       │
                    ▼                       ▼                       ▼
    ┌───────────────────────┐ ┌───────────────────────┐ ┌─────────────────────┐
    │   app.octile.eu.cc    │ │   api.octile.eu.cc    │ │ packs.octile.eu.cc  │
    │                       │ │                       │ │                     │
    │   GitLab Pages        │ │   Cloudflare Worker   │ │   Static hosting    │
    │                       │ │                       │ │                     │
    │   Static assets:      │ │   Proxy + auth:       │ │   Pack files:       │
    │   - index.html        │ │   - CORS              │ │   - release.json    │
    │   - app.min.js        │ │   - HMAC signing      │ │   - *.opk           │
    │   - style.css         │ │   - Cookie UUID       │ │                     │
    │   - config.json       │ │   - OAuth redirects   │ │   Independent from  │
    │   - sw.js             │ │   - Feedback           │ │   app deploys       │
    │   - icons/            │ │                       │ │                     │
    │   - ota/              │ │   Routes:             │ │   Mirrors:          │
    │                       │ │   /health             │ │   (China CDN, etc.) │
    │   Deployed by:        │ │   /version            │ │                     │
    │   GitHub Actions      │ │   /puzzle/{n}         │ └─────────────────────┘
    │   (force-push)        │ │   /level/{lv}/puzzle/ │
    │                       │ │   /levels             │
    │   Also on:            │ │   /score              │
    │   mtaleon.github.io   │ │   /scoreboard         │
    │   (gh-pages branch)   │ │   /leaderboard        │
    └───────────────────────┘ │   /auth/*             │
                              │   /feedback           │
                              └───────────┬───────────┘
                                          │
                                          │ HTTPS (proxied)
                                          │ + HMAC header
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │  m.taleon.work.gd     │
                              │                       │
                              │  Backend (FastAPI)    │
                              │  Docker container     │
                              │                       │
                              │  - Puzzle data        │
                              │  - Score storage      │
                              │  - Auth (JWT + OTP)   │
                              │  - Leaderboard / ELO  │
                              │  - League system      │
                              │  - Daily tasks        │
                              │  - Progress sync      │
                              │  - Pack generation    │
                              │    scripts live here  │
                              │                       │
                              │  Data:                │
                              │  - octile_puzzle_data │
                              │  - difficulty_levels  │
                              │  - SQLite DB          │
                              └───────────────────────┘
```

## Data Flow

### Puzzle Resolution (client startup)

```
Client starts
  │
  ├─ MiniPack (embedded, instant, 99 base puzzles, no ordering)
  │
  ├─ Load FullPack from IDB ───── found? ──→ use pack ordering (v2)
  │                                  │
  │                                  no
  │                                  │
  ├─ Fetch release.json ◄───────────┘
  │   from packs.octile.eu.cc
  │   │
  │   ├─ newer version? ──→ download .opk (primary URL or mirrors)
  │   │                     verify SHA-256 + Ed25519
  │   │                     store in IDB → activate
  │   │
  │   └─ up to date ──→ done
  │
  └─ API fallback (if no pack)
      GET api.octile.eu.cc/level/easy/puzzle/15
      → Worker → Backend → puzzle_number
```

### Score Submission

```
Client solves puzzle
  │
  POST api.octile.eu.cc/score
  │
  Worker (Cloudflare)
  ├─ CORS check
  ├─ Cookie UUID → X-Player-UUID header
  ├─ HMAC signature
  └─ Forward to backend
      │
      Backend (FastAPI)
      ├─ Verify solution
      ├─ data_version compatibility check
      ├─ Calculate grade (S/A/B)
      ├─ Update ELO
      ├─ Store score
      └─ Return { grade, exp, elo, ... }
```

### Pack Release (independent from app)

```
Developer (local / xsw repo)
  │
  python scripts/generate-pack.py --key ...
  │
  ├─ octile-pack-YYYYMMDD.opk  ──→ upload to any URL
  └─ release.json               ──→ deploy to packs.octile.eu.cc
                                     (update .opk URL + mirrors)

  No app update needed.
  All clients auto-download on next launch.
```

## Domain Responsibilities

| Domain | Host | Purpose | Deploy |
|--------|------|---------|--------|
| `app.octile.eu.cc` | GitLab Pages | Web app (HTML/JS/CSS) | GitHub Actions → GitLab force-push |
| `api.octile.eu.cc` | Cloudflare Worker | API proxy (CORS, auth, HMAC) | `wrangler deploy` |
| `m.taleon.work.gd` | Docker (self-hosted) | Backend (FastAPI, DB, puzzle data) | `xdeploy` |
| `packs.octile.eu.cc` | Static hosting | Pack files (release.json, .opk) | Manual / independent |
| `mtaleon.github.io` | GitHub Pages | Legacy web app mirror | gh-pages branch |

## Repo Responsibilities

| Repo | Branch | Contains |
|------|--------|----------|
| `octile` | `main` | Client source (JS, HTML, CSS), build scripts, CI workflows, Electron, Android, iOS |
| `xsw` | `master` | Backend (FastAPI), puzzle data, difficulty levels, pack generation scripts, docs |

## Environment Variables

### Backend (`xsw`)

| Var | Default | Purpose |
|-----|---------|---------|
| `OCTILE_ORDERING` | `v2` | Puzzle ordering version (`v0`/`v1`/`v2`). Set to `v1` for backward compat with old clients. |
| `OCTILE_DB_PATH` | `octile.db` | SQLite database path |
| `OCTILE_JWT_SECRET` | (insecure default) | JWT signing secret |

### Worker (`octile-proxy`)

| Var | Purpose |
|-----|---------|
| `WORKER_HMAC_SECRET` | HMAC signing for backend requests |
| `BACKEND_URL` | Backend origin URL |

## Trust Model

```
                    Trusted                     Untrusted
              ┌──────────────────┐     ┌──────────────────────┐
              │                  │     │                       │
              │  Ed25519 key     │     │  GitLab Pages CDN     │
              │  Pack signature  │     │  Cloudflare CDN       │
              │  Backend DB      │     │  Any .opk mirror      │
              │                  │     │  release.json host     │
              └──────────────────┘     └──────────────────────┘
                       │                         │
                       │    sign                  │    serve
                       ▼                         ▼
              ┌──────────────────────────────────────────────┐
              │                  Client                      │
              │                                              │
              │  Verifies: SHA-256 hash + Ed25519 signature  │
              │  Rejects:  any tampered or mismatched data   │
              │  Falls back: API → MiniPack → random puzzle  │
              └──────────────────────────────────────────────┘
```
