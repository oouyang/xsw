# Background Job System

## Overview

The background job system automatically pre-caches book metadata and chapter lists when users browse categories. This improves user experience by reducing load times when accessing book details.

## Architecture

### Components

1. **BackgroundJobManager** (`background_jobs.py`)
   - Thread-safe job queue with priority support
   - Configurable worker threads (default: 2)
   - Rate limiting to avoid overloading the scraping target
   - Deduplication (same book not queued multiple times)
   - Job history tracking (completed and failed jobs)

2. **Worker Threads**
   - Process jobs from the queue asynchronously
   - Each job fetches book info and chapter list
   - Stores data to SQLite database and memory cache
   - Rate-limited to respect the source website

3. **Integration Points**
   - Triggered automatically when listing books in categories
   - Can be manually triggered via admin API
   - Runs in background without blocking HTTP requests

## How It Works

### Automatic Triggering

When a user views a category page (`/categories/{cat_id}/books`):

1. API returns the list of books immediately (no delay)
2. Background jobs are queued for each book on the page
3. Workers process jobs asynchronously:
   - Fetch book metadata (title, author, last chapter, etc.)
   - Fetch all chapter references (number, title, URL)
   - Store to database for future use
4. Next time user accesses that book, data is served from cache instantly

### Job Processing Flow

```
User requests category page
    ↓
API returns book list immediately
    ↓
[Background] Queue sync jobs for books
    ↓
[Worker Thread] Pick job from queue
    ↓
[Worker Thread] Check if already cached
    ↓
[Worker Thread] Fetch from web if needed
    ↓
[Worker Thread] Store to database
    ↓
[Worker Thread] Mark job as completed
```

### Deduplication & Rate Limiting

- **Deduplication**: Same book won't be queued if already active or recently completed
- **Rate Limiting**: Configurable delay between jobs (default: 2 seconds)
- **Priority**: Higher priority jobs processed first (manual triggers get priority 10)
- **Recently Completed**: Books synced within last 5 minutes won't be re-queued

## Configuration

Environment variables (set in `.env`):

```bash
# Number of background worker threads
BG_JOB_WORKERS=2

# Rate limit between jobs (seconds)
BG_JOB_RATE_LIMIT=2.0
```

## API Endpoints

### Get Job Statistics

```bash
GET /xsw/api/admin/jobs/stats
```

Response:
```json
{
  "queue_size": 5,
  "active_jobs": 1,
  "active_job_ids": ["1721851"],
  "completed_count": 42,
  "failed_count": 2,
  "failed_jobs": {
    "1234567": {
      "failed_at": "2026-01-21T12:00:00",
      "error": "Timeout error"
    }
  },
  "workers": 2,
  "running": true
}
```

### Manually Trigger Book Sync

```bash
POST /xsw/api/admin/jobs/sync/{book_id}?priority=10
```

Response:
```json
{
  "status": "queued",
  "book_id": "1721851",
  "priority": 10
}
```

### Clear Job History

```bash
POST /xsw/api/admin/jobs/clear_history
```

Response:
```json
{
  "status": "cleared",
  "message": "Job history cleared"
}
```

### Health Check (includes job stats)

```bash
GET /xsw/api/health
```

Response:
```json
{
  "status": "ok",
  "base_url": "https://m.xsw.tw",
  "db_path": "xsw_cache.db",
  "cache_stats": { ... },
  "job_stats": {
    "queue_size": 5,
    "active_jobs": 1,
    "completed_count": 42,
    "workers": 2,
    "running": true
  }
}
```

## Disabling Background Sync

To disable automatic background syncing for a specific request:

```bash
GET /xsw/api/categories/{cat_id}/books?bg_sync=false
```

This can be useful for:
- Debugging
- Reducing server load
- Testing without side effects

## Benefits

### 1. Faster User Experience
- Book details load instantly from cache
- No waiting for web scraping when browsing
- Smooth navigation between books

### 2. Reduced Load on Source Website
- Rate-limited requests (default: 1 request per 2 seconds)
- Deduplication prevents redundant scraping
- Data cached in database for long-term reuse

### 3. Proactive Caching
- Data ready before user requests it
- Anticipates user browsing patterns
- Background processing doesn't block API responses

### 4. Scalability
- Configurable number of workers
- Thread-safe queue management
- Handles high traffic gracefully

## Monitoring

### Check Job Queue Status

```bash
curl http://localhost:8000/xsw/api/admin/jobs/stats
```

### Watch Logs

```bash
docker logs -f xsw
```

Look for log messages:
- `[BackgroundJobManager] Queued sync job for book {id}`
- `[BG] Cached book info for {id}`
- `[BG] Cached {n} chapter references for {id}`
- `[Sync] Completed sync for book {id}`

### Check Database

```bash
docker exec -it xsw sqlite3 xsw_cache.db

# Check cached books
SELECT id, name, last_chapter_num FROM books;

# Check cached chapters
SELECT book_id, COUNT(*) as chapter_count FROM chapters GROUP BY book_id;
```

## Troubleshooting

### Jobs Not Processing

1. Check if workers are running:
   ```bash
   curl http://localhost:8000/xsw/api/admin/jobs/stats
   ```
   Verify `"running": true`

2. Check for failed jobs:
   ```bash
   curl http://localhost:8000/xsw/api/admin/jobs/stats | jq '.failed_jobs'
   ```

3. Check container logs:
   ```bash
   docker logs xsw --tail 100
   ```

### High Queue Size

If queue size keeps growing:

1. Increase number of workers:
   ```bash
   # In .env
   BG_JOB_WORKERS=4
   ```

2. Reduce rate limit (faster processing):
   ```bash
   # In .env
   BG_JOB_RATE_LIMIT=1.0
   ```

3. Clear queue by restarting:
   ```bash
   docker restart xsw
   ```

### Memory Usage

If memory usage is high:

1. Reduce number of workers:
   ```bash
   # In .env
   BG_JOB_WORKERS=1
   ```

2. Clear job history periodically:
   ```bash
   curl -X POST http://localhost:8000/xsw/api/admin/jobs/clear_history
   ```

## Future Enhancements

Potential improvements:

1. **Persistent Queue**: Store queue in database to survive restarts
2. **Retry Logic**: Automatic retry for failed jobs with exponential backoff
3. **Priority Scheduling**: Different priorities for different job types
4. **Job Expiration**: Remove stale jobs after certain time
5. **Metrics Dashboard**: Web UI to monitor job status
6. **Webhook Notifications**: Alert when jobs fail or queue grows too large
7. **Distributed Workers**: Support multiple instances with shared queue

## Implementation Details

### Thread Safety

- All shared state protected by threading locks
- Queue operations are atomic
- No race conditions in job processing

### Error Handling

- Failed jobs tracked with error messages
- Workers continue processing even if one job fails
- Errors logged for debugging

### Graceful Shutdown

- Workers stop cleanly when application shuts down
- In-progress jobs complete before shutdown
- 5-second timeout for worker cleanup

## Example Scenario

**User browses Fantasy category:**

1. User opens `/categories/1/books?page=1`
   - API returns 20 books instantly
   - 20 background jobs queued

2. Worker 1 & 2 start processing
   - Worker 1: Syncs book #1721851
   - Worker 2: Syncs book #1721852
   - Rate limit: 2 seconds between jobs

3. User clicks on book #1721851
   - Book info loaded from cache (instant)
   - Chapter list loaded from cache (instant)
   - No web scraping needed

4. User navigates to chapter
   - Chapter metadata available instantly
   - Chapter content fetched on-demand

**Result**: Smooth, fast browsing experience with minimal source website load.
