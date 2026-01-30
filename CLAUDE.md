# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

看小說 (XSW) is a full-stack Chinese novel reading platform with a **FastAPI backend** and **Vue 3 + Quasar frontend**. The architecture is intentionally **simple and synchronous** - all operations happen on-demand when requested by the frontend. There are no background workers, automatic syncing, or job queues.

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
- **`main_optimized.py`** - Main FastAPI application (1540 lines)
  - All REST endpoints
  - On-demand chapter/book fetching
  - Search, admin, email endpoints

- **`cache_manager.py`** - Hybrid caching system
  - `CacheManager` class with get/store methods
  - Thread-safe TTL cache implementation

- **`parser.py`** - HTML parsing with BeautifulSoup
  - `fetch_chapters_from_liebiao()` - **Uses sequential indexing**
  - `parse_book_info()` - Extract book metadata
  - `chapter_title_to_number()` - Supports Chinese numerals

- **`db_models.py`** - SQLAlchemy ORM models
  - `Book`, `Chapter`, `SmtpSettings` tables

### Frontend Core Files
- **`src/stores/books.ts`** - Pinia store for book state (676 lines)
  - **CRITICAL**: All pagination uses number-based filtering (see rule #1)
  - Two-phase loading: nearby pages first, then background load all
  - Chapter validation with retry logic

- **`src/pages/ChapterPage.vue`** - Chapter reading view
  - Keyboard navigation (arrow keys)
  - Adaptive loading with progress feedback

- **`src/services/bookApi.ts`** - Axios API client
  - Type-safe wrappers for backend endpoints

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

### Data Consistency
- Backend sorts chapters after fetching: `all_chapters.sort(key=lambda c: c.number)`
- Frontend **always** searches by number, never by index
- Use `findIndex()` to locate chapters, never calculate index from number

## Common Patterns

### Adding New API Endpoints
1. Add endpoint in `main_optimized.py`
2. Use `cache_mgr.cache_manager` for caching
3. Handle `HTTPException` for errors
4. Return Pydantic models for type safety

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

### Frontend
- Vue 3.5+ with Composition API
- Quasar 2.16+ for UI components
- Pinia 3.0+ for state management
- OpenCC-JS for Traditional/Simplified Chinese conversion

## Environment Configuration

Required `.env` variables:
```bash
BASE_URL=https://m.xsw.tw      # Scraping target
DB_PATH=xsw_cache.db           # SQLite database
CACHE_TTL_SECONDS=900          # Memory cache TTL
HTTP_TIMEOUT=10                # Request timeout
```

## Testing

Currently no automated tests. Manual testing workflow:
1. Start backend: `uvicorn main_optimized:app --reload`
2. Start frontend: `npm run dev`
3. Test via browser at http://localhost:9000
4. Check API docs at http://localhost:8000/xsw/api/docs

## Documentation References

- **README.md** - Full feature overview and setup
- **TWO_PHASE_LOADING.md** - Frontend loading strategy
- **SEARCH_API.md** - Full-text search implementation
- **ADMIN_PANEL.md** - Admin features
- **SQLITE_BATCH_FIX.md** - Batch commit optimization

## Recent Major Changes

1. **Sequential Indexing** (Jan 2026) - Changed from parsed chapter numbers to sequential indices (1, 2, 3, ...)
2. **Removed Background Jobs** (Jan 2026) - Simplified backend by removing all automatic sync systems
3. **Number-Based Filtering** (Jan 2026) - Fixed all locations that assumed `chapter.number = index + 1`

When making changes, always verify that the sequential indexing and number-based filtering principles are maintained.
