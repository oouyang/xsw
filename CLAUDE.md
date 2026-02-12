# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

看小說 (XSW) is a full-stack Chinese novel reading platform with a **FastAPI backend** and **Vue 3 + Quasar frontend**. The scraping source is **czbooks.net** (previously m.xsw.tw). The architecture is intentionally **simple and synchronous** - all operations happen on-demand when requested by the frontend. There are no background workers, automatic syncing, or job queues.

## Commands

### Backend Development
```bash
# Run backend (development)
cd /opt/ws/xsw
uvicorn main_optimized:app --reload --port 8000

# Access API docs
open http://localhost:8000/xsw/api/docs

# Check syntax
python3 -m py_compile main_optimized.py
```

### Frontend Development
```bash
# Install dependencies
npm install

# Run Quasar dev server (hot reload)
npm run dev   # Opens at http://localhost:9000

# Build for production
npm run build

# Lint
npm run lint

# Format code
npm run format
```

### Docker Deployment
```bash
# Build and run all services
docker compose -f compose.yml -f docker/build.yml up -d --build

# Backend only
docker compose -f compose.yml -f docker/build.yml up -d xsw --build

# Frontend only
docker compose -f compose.yml -f docker/build.yml up -d web --build

# View logs
docker logs xsw --tail 100 -f
```

## Critical Architecture Principles

### 1. Sequential Indexing System

**CRITICAL RULE**: Chapter numbers are **sequential indices** (1, 2, 3, ...), NOT parsed from titles.

**Why**: Some chapter titles don't contain numbers, causing gaps if parsed. Sequential indexing prevents gaps.

**Implementation**:
- `parser.py::fetch_chapters_from_liebiao()` uses `start_index` parameter
- Pagination maintains continuity: if page 1 ends at chapter 50, page 2 starts at 51
- Backend: [main_optimized.py:551-562](main_optimized.py#L551-L562)
- Frontend stores chapters as `{ number: int, title: string, url: string }`

**NEVER assume `chapter.number = array_index + 1`**:
- Always use **number-based filtering**: `allChapters.filter(ch => ch.number >= min && ch.number <= max)`
- NEVER use index-based slicing: `allChapters.slice(start, end)` ❌
- This rule was violated in 5 places in books.ts and was fixed in commit history

### 2. 3-Tier Caching Architecture

Cache hierarchy (fastest to slowest):
1. **Memory (TTL Cache)** - Thread-safe, 15min TTL, LRU eviction
2. **SQLite Database** - Persistent, survives restarts
3. **Web Scraping** - Fallback, rate-limited

**Flow**: Check memory → Check DB → Fetch from web → Store to DB → Cache in memory

**Key Files**:
- `cache_manager.py` - Implements all 3 tiers
- `db_models.py` - SQLAlchemy models for Book/Chapter tables

### 3. Simplified Backend (No Background Jobs)

**IMPORTANT**: As of recent refactoring, all background job systems were removed:
- ❌ No `background_jobs.py` usage
- ❌ No `midnight_sync.py` scheduler
- ❌ No `periodic_sync.py` scheduler
- ✅ All operations are **synchronous and on-demand**

This makes the system much simpler to understand and maintain.

## File Architecture

### Backend Core Files
- **`main_optimized.py`** - Main FastAPI application (~2280 lines)
  - All REST endpoints (books, chapters, search, admin, email)
  - User auth + reading progress endpoints
  - OG meta tag injection for social crawlers
  - On-demand chapter/book fetching

- **`cache_manager.py`** - Hybrid caching system
  - `CacheManager` class with get/store methods
  - Thread-safe TTL cache implementation

- **`parser.py`** - HTML parsing with BeautifulSoup (czbooks.net selectors)
  - `fetch_chapters_from_liebiao()` - Parses `ul.chapter-list` (all chapters on one page), **uses sequential indexing**
  - `parse_book_info()` - Parses `div.novel-detail` for book metadata
  - `parse_books()` - Parses `li.novel-item-wrapper` for category book lists
  - `find_categories_from_nav()` - Parses `/c/{slug}` links from nav menu
  - `extract_book_id_from_url()` - Extracts book ID from `/n/{book_id}` URL pattern
  - `extract_text_by_selector()` - CSS selector-based text extraction (for `div.content`)
  - `chapter_title_to_number()` - Supports Chinese numerals

- **`db_models.py`** - SQLAlchemy ORM models
  - `Book`, `Chapter`, `SmtpSettings` tables
  - `User`, `UserOAuth`, `ReadingProgress` tables (reader accounts)

- **`user_auth.py`** - Reader OAuth authentication (separate from admin `auth.py`)
  - Google, Facebook, Apple, WeChat OAuth verification
  - User JWT (30-day expiration, `role: "user"`)
  - `find_or_create_user()` with email-based account merging
  - `require_user_auth` / `optional_user_auth` FastAPI dependencies

### Frontend Core Files
- **`src/stores/books.ts`** - Pinia store for book state (676 lines)
  - **CRITICAL**: All pagination uses number-based filtering (see rule #1)
  - Two-phase loading: nearby pages first, then background load all
  - Chapter validation with retry logic

- **`src/stores/userAuth.ts`** - Pinia store for reader auth state
  - Login/logout actions for all 4 OAuth providers
  - Reactive `isLoggedIn`, `displayName`, `avatarUrl`

- **`src/pages/ChapterPage.vue`** - Chapter reading view
  - Keyboard navigation (arrow keys)
  - Adaptive loading with progress feedback
  - Saves reading progress on chapter load
  - Share button in header card

- **`src/services/bookApi.ts`** - Axios API client
  - Type-safe wrappers for backend endpoints

- **`src/services/userAuthService.ts`** - User auth + progress API client
  - OAuth login, token management, progress CRUD
  - Separate localStorage key (`xsw_user_token`)

- **`src/composables/useReadingHistory.ts`** - Reading history (local-first)
  - localStorage `xsw_reading_history` (max 20 entries)
  - Server sync when logged in (fire-and-forget PUT)
  - `syncOnLogin()` merges local+server by timestamp

- **`src/composables/useShare.ts`** - Share functionality
  - Web Share API (native mobile), platform fallbacks (FB, LINE, Twitter, WeChat QR)

- **`src/components/UserLoginDialog.vue`** - 4-provider login dialog
- **`src/components/ShareMenu.vue`** - Share button with platform menu
- **`src/components/ContinueReadingCard.vue`** - Reading progress card

## State Management Patterns

### Frontend State (Pinia)
```typescript
// books.ts store structure
{
  bookId: string | null,
  info: BookInfo | null,          // Book metadata
  allChapters: ChapterRef[],      // GLOBAL cache of all chapters
  pageChapters: ChapterRef[],     // Current page (derived from allChapters)
  page: number,                   // Current page (1-indexed)
  currentChapterIndex: number     // Index in allChapters array
}
```

**Key Methods**:
- `loadAllChapters()` - Two-phase loading strategy
- `setPage()` - **Uses number-based filtering, not index slicing**
- `validateChapters()` - Checks sorting, gaps, first chapter === 1
- `triggerResync()` - Manual resync with retry logic (max 3)

### Backend Caching Strategy
```python
# Cache key patterns
book_info: f"book:{book_id}"
chapter_content: f"chapter:{book_id}:{chapter_num}"

# Always check memory first, then DB, then web
cached = memory_cache.get(key)
if not cached:
    cached = db_query(...)
if not cached:
    cached = web_scrape(...)
    db_store(cached)
    memory_cache.set(key, cached)
```

## Important Constraints

### Number-Based Filtering (Critical)
```typescript
// ✅ CORRECT - Number-based filtering
const currentPageFirstChapter = (page - 1) * pageSize + 1;
const currentPageLastChapter = page * pageSize;
pageChapters = allChapters.filter(
  ch => ch.number >= currentPageFirstChapter && ch.number <= currentPageLastChapter
);

// ❌ WRONG - Index-based slicing (assumes chapter.number = index + 1)
const start = (page - 1) * pageSize;
const end = start + pageSize;
pageChapters = allChapters.slice(start, end);  // DON'T DO THIS
```

### czbooks.net URL Patterns
| Resource | URL Pattern | Example |
|----------|------------|---------|
| Book detail | `/n/{book_id}` | `https://czbooks.net/n/cr382b` |
| Chapter | `/n/{book_id}/{chapter_id}` | `https://czbooks.net/n/cr382b/crdic` |
| Category | `/c/{slug}` | `https://czbooks.net/c/xuanhuan` |
| Category page N | `/c/{slug}/{page}` | `https://czbooks.net/c/xuanhuan/2` |
| Search | `/s?q=...` | `https://czbooks.net/s?q=keyword` |

**Key differences from old m.xsw.tw**:
- Book IDs are **alphanumeric** (e.g. `cr382b`), not numeric
- Chapter IDs are **alphanumeric** (e.g. `crdic`), not numeric
- Categories use **slugs** (`xuanhuan`), not numeric IDs
- **All chapters on one page** — no pagination for chapter lists
- Protocol-relative URLs (`//czbooks.net/...`) must be normalized to `https:`

### API Parameters
- `?all=true` returns ALL chapters (no pagination)
- `?www=true` fetches from home page only (latest ~10 chapters, may be incorrectly numbered)
- `?nocache=true` bypasses cache

### Chapter Validation Rules
With sequential indexing, validation is strict:
1. Chapters must be sorted by number
2. **Gap must be exactly 1** (no skips allowed)
3. **First chapter must be exactly 1**
4. Total count should match book info (±5% tolerance)

### User Auth & Progress API

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/user/auth/google` | POST | — | Google login `{id_token}` |
| `/user/auth/facebook` | POST | — | Facebook login `{access_token}` |
| `/user/auth/apple` | POST | — | Apple login `{id_token}` |
| `/user/auth/wechat` | POST | — | WeChat login `{code}` |
| `/user/auth/verify` | GET | User JWT | Verify token |
| `/user/auth/me` | GET | User JWT | Get profile |
| `/user/progress` | GET | User JWT | List all progress |
| `/user/progress/{book_id}` | GET | User JWT | Get progress for one book |
| `/user/progress/{book_id}` | PUT | User JWT | Upsert progress |
| `/user/progress/{book_id}` | DELETE | User JWT | Delete progress |

**JWT differentiation**: Admin tokens have `role: "admin"`, user tokens have `role: "user"`. Different expiration (24h vs 30 days). Separate localStorage keys (`xsw_admin_token` vs `xsw_user_token`).

**Account merging**: When a new OAuth login occurs, `find_or_create_user()` checks: (1) exact `(provider, provider_user_id)` match, (2) email match across providers, (3) create new user. This allows a reader to link Google + Facebook to one account if they share an email.

### Data Consistency
- Backend sorts chapters after fetching: `all_chapters.sort(key=lambda c: c.number)`
- Frontend **always** searches by number, never by index
- Use `findIndex()` to locate chapters, never calculate index from number

## Routing Architecture

### API Router Pattern

**CRITICAL**: All API endpoints use `api_router`, NOT direct `@app` decorators.

```python
# main_optimized.py structure:
api_router = APIRouter()  # Line 169

# Define ALL routes on api_router
@api_router.get("/health")
def health():
    pass

# Include router at END of file (line 1702)
app.include_router(api_router, prefix="/xsw/api")
```

**Why This Matters**:
- Routes must be defined BEFORE router inclusion
- Never mount StaticFiles at `/` (blocks all routes)
- API prefix `/xsw/api` added via `include_router()`
- See [docs/ROUTING_FIX.md](docs/ROUTING_FIX.md) for full technical details

### Static File Serving

SPA and static assets are served without blocking API routes:
- `/` → SPA index.html (route handler)
- `/assets/*` → Mounted StaticFiles
- `/icons/*` → Mounted StaticFiles
- `/{file}.{ext}` → Route handler for config.json, favicon.ico, etc.
- SPA fallback middleware for client-side routing

## Common Patterns

### Adding New API Endpoints
1. Add endpoint in `main_optimized.py` using `@api_router` decorator
2. Define route BEFORE the `app.include_router()` call (before line 1702)
3. Use `cache_mgr.cache_manager` for caching
4. Handle `HTTPException` for errors
5. Return Pydantic models for type safety

Example:
```python
# Add around line 300-1650 (before router inclusion)
@api_router.get("/my-endpoint")
def my_endpoint():
    return {"status": "ok"}
```

### Adding Frontend Features
1. Create API client method in `src/services/bookApi.ts`
2. Add state to Pinia store if needed
3. Use Vue 3 Composition API with `<script setup>`
4. Leverage Quasar components (`q-btn`, `q-card`, etc.)

### Debugging Cache Issues
```bash
# Check cache stats
curl http://localhost:8000/xsw/api/admin/stats

# Clear memory cache
curl -X POST http://localhost:8000/xsw/api/admin/cache/clear

# Delete chapter cache for specific book
curl -X DELETE http://localhost:8000/xsw/api/admin/cache/chapters/{book_id}
```

## Key Dependencies

### Backend
- FastAPI 0.100+ for API framework
- SQLAlchemy for ORM
- BeautifulSoup4 for HTML parsing
- Requests for HTTP (with SSL verification disabled for corporate proxy)
- PyJWT for user + admin JWT tokens (RS256 for Apple, HS256 for others)

### Frontend
- Vue 3.5+ with Composition API
- Quasar 2.16+ for UI components
- Pinia 3.0+ for state management
- OpenCC-JS for Traditional/Simplified Chinese conversion
- qrcode for WeChat QR share

## Environment Configuration

Required `.env` variables:
```bash
BASE_URL=https://czbooks.net   # Scraping target (czbooks.net)
DB_PATH=xsw_cache.db           # SQLite database
CACHE_TTL_SECONDS=900          # Memory cache TTL
HTTP_TIMEOUT=10                # Request timeout
AUTH_ENABLED=true              # Enable/disable authentication (default: true)
```

### Social Login Environment Variables (Optional)

All are optional — providers without credentials are simply unavailable:

```bash
# Google (shared with admin OAuth)
GOOGLE_CLIENT_ID=...

# Facebook
FACEBOOK_APP_ID=...
FACEBOOK_APP_SECRET=...

# Apple Sign-In
APPLE_CLIENT_ID=...
APPLE_TEAM_ID=...
APPLE_KEY_ID=...
APPLE_PRIVATE_KEY=...          # PEM-encoded private key

# WeChat
WECHAT_APP_ID=...
WECHAT_APP_SECRET=...

# User JWT
USER_JWT_EXPIRATION_DAYS=30    # Default 30 days (vs admin's 24h)
```

### Authentication Control

Set `AUTH_ENABLED=false` to disable authentication:
- All admin endpoints accessible without JWT tokens
- Useful for local development and testing
- Not recommended for production deployments

```bash
# Development without auth
export AUTH_ENABLED=false
uvicorn main_optimized:app --reload

# Production with auth (default)
export AUTH_ENABLED=true
docker compose up -d
```

## Testing

### Automated Tests (Backend)

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_parser.py -v
pytest tests/test_cache.py -v
pytest tests/test_api.py -v
```

Test suite (122 tests, all offline with mocked HTML):
- **`tests/test_parser.py`** (~45 tests) — Pure parser function unit tests: `extract_text_by_id`, `extract_text_by_selector`, `extract_chapter_title`, `chinese_to_arabic`, `chapter_title_to_number`, `extract_book_id_from_url`, `find_categories_from_nav`, `parse_books`, `parse_book_info`, `fetch_chapters_from_liebiao`, `_normalize_czbooks_url`
- **`tests/test_cache.py`** (16 tests) — TTLCache and CacheManager tests with in-memory SQLite
- **`tests/test_api.py`** (12 tests) — API endpoint integration tests via FastAPI TestClient with mocked `fetch_html`
- **`tests/test_user_auth.py`** (13 tests) — User JWT create/decode, account merging (same provider, email merge, no-email isolation), token rejection
- **`tests/test_progress_api.py`** (10 tests) — Reading progress CRUD, auth enforcement, user data isolation

Key test design:
- `tests/html_fixtures.py` — Inline HTML snippets matching czbooks.net structure
- `tests/conftest.py` — `FetchMock` class patches `main_optimized.fetch_html`; `AUTH_ENABLED=false` and `DB_PATH=:memory:` set before app import
- No network calls — all HTTP responses are mocked
- Each test gets a fresh in-memory SQLite database via TestClient lifespan

### Automated Tests (Frontend)

```bash
# Run all frontend tests
npm test

# Run with verbose output
npx vitest run --reporter=verbose

# Run specific test file
npx vitest run src/__tests__/utils.test.ts
npx vitest run src/__tests__/basePath.test.ts
npx vitest run src/__tests__/bookStore.test.ts

# Watch mode (re-runs on file changes)
npx vitest
```

Test suite (59 tests, all offline with mocked imports):
- **`src/__tests__/utils.test.ts`** (14 tests) — Pure utility functions: `toArr`, `dedupeBy`, `normalizeNum`, `syncLastChapter`
- **`src/__tests__/basePath.test.ts`** (15 tests) — Base path detection: `detectBasePath`, `getFullPath`, `getAssetPath`
- **`src/__tests__/bookStore.test.ts`** (30 tests) — Pinia book store: `setBookId`, `setPage`, `setChapter`, `maxPages`, `pageSlice`, `nextChapter`/`prevChapter`, `validateChapters`

Key test design:
- `vi.mock('quasar')` — Stubs `LocalStorage`, `Dialog`, `Dark` to break Quasar runtime dependency
- `vi.mock('src/services/bookApi')` — Stubs API calls to break `boot/axios` → `#q-app/wrappers` chain
- `vi.mock('src/services/useAppConfig')` — Breaks circular import with utils.ts
- Uses real `createPinia()` + `setActivePinia()` per test for isolated store state
- No network calls, no Quasar runtime needed

### Manual Testing

1. Start backend: `uvicorn main_optimized:app --reload`
2. Start frontend: `npm run dev`
3. Test via browser at http://localhost:9000
4. Check API docs at http://localhost:8000/xsw/api/docs

## Documentation References

- **README.md** - Full feature overview and setup
- **docs/TWO_PHASE_LOADING.md** - Frontend loading strategy
- **docs/SEARCH_API.md** - Full-text search implementation
- **docs/ADMIN_PANEL.md** - Admin features
- **docs/SQLITE_BATCH_FIX.md** - Batch commit optimization
- **docs/ROUTING_FIX.md** - API routing architecture and 404 fix explanation

## Recent Major Changes

### February 2026

1. **Social Login, Share & Continue Reading** (Feb 12, 2026) - Major user-facing feature set
   - **Social login** for readers via Google, Facebook, Apple, WeChat OAuth
   - New DB tables: `User`, `UserOAuth`, `ReadingProgress`
   - **Reading progress**: local-first (`localStorage`), server-synced when logged in
   - **Continue Reading** section on dashboard with progress cards
   - **Share** book/chapter links via Web Share API, Facebook, LINE, Twitter, WeChat QR
   - **OG meta tags** for social crawler previews (Facebook, Twitter, LINE)
   - User avatar/login button in toolbar
   - WeChat redirect callback route
   - 23 new backend tests (user auth + progress API)
   - i18n translations for en-US, zh-TW, zh-CN

2. **czbooks.net Migration** (Feb 11, 2026) - Switched scraping source from m.xsw.tw to czbooks.net
   - m.xsw.tw returned 404 for all pages; czbooks.net is a working alternative
   - Completely different HTML structure and URL scheme:
     - Book URLs: `/n/{book_id}` (alphanumeric IDs like `cr382b`)
     - Chapter URLs: `/n/{book_id}/{chapter_id}`
     - Category URLs: `/c/{slug}` (e.g. `/c/xuanhuan`)
     - All chapters listed on single book page (no pagination)
   - Rewrote all parser functions for czbooks.net CSS selectors
   - Simplified `fetch_all_chapters_from_pagination()` (single page fetch)
   - Category `cat_id` changed from `int` to `str` (slug-based)
   - Added `extract_text_by_selector()` for CSS selector-based content extraction
   - Legacy parser fallbacks retained for backward compatibility with cached data

2. **API Routing Refactor** (Feb 1, 2026) - Fixed 404 errors for all API endpoints
   - Introduced APIRouter pattern for all `/xsw/api/*` routes
   - Removed blocking StaticFiles mount at root
   - Proper route precedence over static file serving
   - See [docs/ROUTING_FIX.md](docs/ROUTING_FIX.md) for technical details

2. **Authentication Control** (Feb 1, 2026) - Added `AUTH_ENABLED` environment variable
   - Can disable authentication for development with `AUTH_ENABLED=false`
   - All admin endpoints accessible without JWT when disabled
   - Configured in [auth.py](auth.py#L17) and [docker/Dockerfile](docker/Dockerfile#L40)

3. **Docker Build Optimization** (Feb 1, 2026) - Added pip cache mounting
   - Speeds up rebuilds by caching Python packages
   - Similar to existing npm cache in builder stage
   - See [docker/Dockerfile:25](docker/Dockerfile#L25)

### January 2026

1. **Sequential Indexing** (Jan 2026) - Changed from parsed chapter numbers to sequential indices (1, 2, 3, ...)
2. **Removed Background Jobs** (Jan 2026) - Simplified backend by removing all automatic sync systems
3. **Number-Based Filtering** (Jan 2026) - Fixed all locations that assumed `chapter.number = index + 1`

## Important Principles

When making changes, always verify:
1. **Sequential indexing** - Chapters numbered 1, 2, 3... regardless of title
2. **Number-based filtering** - Never use index slicing, always filter by chapter.number
3. **Router pattern** - All API routes use `@api_router`, included at end of file
4. **No root mounts** - Never mount StaticFiles at `/`, use selective paths only
5. **Dual auth systems** - Admin auth (`auth.py`, `role: "admin"`) and user auth (`user_auth.py`, `role: "user"`) are separate. Don't mix JWT tokens.
6. **Local-first reading history** - Always write to localStorage first, server sync is fire-and-forget. Never block UI on server calls.
