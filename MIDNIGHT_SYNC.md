# Midnight Sync Queue System

A deferred book synchronization system that tracks accessed books and syncs them at midnight with rate limiting to avoid blocking by m.xsw.tw.

## Features

- **Access Tracking**: Automatically tracks when users access books
- **Automatic Unfinished Book Sync**: Automatically syncs all unfinished books every night (NEW! 🆕)
- **Persistent Queue**: Uses database to store pending sync jobs (survives restarts)
- **Scheduled Syncing**: Runs at configurable time (default: midnight)
- **Slow Rate Limiting**: Delays between books to avoid rate limiting (default: 5 seconds)
- **Priority Support**: Books with higher access counts are synced first
- **Status Tracking**: Tracks sync status (pending, syncing, completed, failed)

## How It Works

1. **Access Tracking**: When a user accesses a book (GET `/books/{book_id}`), the book is added to the pending sync queue with priority 0
2. **Automatic Unfinished Book Detection**: At midnight, the system automatically:
   - Queries all books from database where `status != "已完成"` (not completed)
   - Adds/updates these books in the sync queue with priority 1
   - Ensures all ongoing books are kept up-to-date
3. **Queue Storage**: Books are stored in the `pending_sync_queue` database table with:
   - `book_id`: The book identifier
   - `accessed_at`: Last access time
   - `access_count`: Number of times accessed
   - `priority`: Priority for syncing (0 = user-accessed, 1 = auto-added unfinished)
   - `sync_status`: Current status (pending/syncing/completed/failed)
4. **Scheduler**: A background thread checks every minute if it's time to run the sync
5. **Midnight Sync**: At the configured time:
   - **Step 1**: Adds all unfinished books to the queue
   - **Step 2**: Fetches all pending books from the queue
   - Sorts by priority (higher first) and access count (higher first)
   - Syncs each book using the existing background job system
   - Waits between books according to the rate limit
   - Updates status as each book completes

## Configuration

Set these environment variables in your `.env` file:

```bash
# Midnight sync configuration
MIDNIGHT_SYNC_HOUR=0              # Hour to run sync (0-23), default: 0 (midnight)
MIDNIGHT_SYNC_MINUTE=0            # Minute to run sync (0-59), default: 0
MIDNIGHT_SYNC_RATE_LIMIT=5.0      # Seconds between syncing each book, default: 5.0
```

## API Endpoints

### Get Queue Statistics
```
GET /admin/midnight-sync/stats
```

Returns:
```json
{
  "total": 100,
  "pending": 45,
  "syncing": 2,
  "completed": 50,
  "failed": 3,
  "last_sync_date": "2026-01-21T00:00:05.123456",
  "next_sync_time": "00:00",
  "slow_rate_limit": 5.0
}
```

### Enqueue Unfinished Books (NEW! 🆕)
```
POST /admin/midnight-sync/enqueue-unfinished
```

Manually enqueue all unfinished books (status != '已完成') to the sync queue without waiting for midnight.

Returns:
```json
{
  "status": "success",
  "added_count": 23,
  "message": "Added 23 unfinished books to sync queue"
}
```

**Use cases:**
- Testing the automatic sync feature
- Immediately syncing newly added books
- Recovering from failed syncs

### Clear Completed/Failed Entries
```
POST /admin/midnight-sync/clear-completed
```

Removes completed and failed entries from the queue to keep it clean.

### Manually Trigger Sync
```
POST /admin/midnight-sync/trigger
```

Immediately starts the full midnight sync process (including adding unfinished books) without waiting for the scheduled time.

## Database Schema

Table: `pending_sync_queue`

| Column | Type | Description |
|--------|------|-------------|
| book_id | String (PK) | Book identifier |
| added_at | DateTime | When first added to queue |
| accessed_at | DateTime | Last access time |
| access_count | Integer | Number of times accessed |
| priority | Integer | Sync priority (higher = first) |
| last_sync_attempt | DateTime | Last sync attempt time |
| sync_status | String | pending/syncing/completed/failed |

Indexes:
- `idx_sync_status` on `sync_status`
- `idx_accessed_at` on `accessed_at`

## Example Usage

1. User accesses a book:
   ```
   GET /books/123
   ```
   → Book 123 is automatically added to the pending sync queue

2. User accesses the same book again:
   ```
   GET /books/123
   ```
   → Book 123's `access_count` is incremented and `accessed_at` is updated

3. At midnight (00:00):
   - Scheduler wakes up and sees it's time to sync
   - Fetches all pending books ordered by priority and access count
   - Syncs each book with 5-second delays between them
   - Updates status as each completes

4. Check queue status:
   ```
   GET /admin/midnight-sync/stats
   ```

5. Manually trigger sync during the day (for testing):
   ```
   POST /admin/midnight-sync/trigger
   ```

## Architecture

### Components

1. **`midnight_sync.py`**: Core scheduler implementation
   - `MidnightSyncScheduler`: Main scheduler class
   - `track_book_access()`: Adds/updates books in queue
   - `_scheduler_loop()`: Background thread that checks for sync time
   - `_run_midnight_sync()`: Processes all pending books

2. **`db_models.py`**: Database model
   - `PendingSyncQueue`: SQLAlchemy model for the queue table

3. **`main_optimized.py`**: Integration
   - Initializes scheduler on startup
   - Tracks book accesses in `get_book_info()`
   - Exposes admin API endpoints

### Integration with Existing System

The midnight sync system integrates with the existing `BackgroundJobManager`:
- Midnight sync adds books to the existing background job queue
- Background workers handle the actual scraping
- Rate limiting at two levels:
  1. Midnight sync rate limit (5s between books being queued)
  2. Background job rate limit (2s between actual scraping operations)

This two-tier approach ensures:
- Books are queued slowly to avoid overwhelming the system
- Each individual scraping operation respects rate limits
- No changes needed to existing scraping logic

## Benefits

1. **Non-blocking**: Book access is instant, sync happens later
2. **Smart Scheduling**: Syncs during off-peak hours
3. **Rate Limit Protection**: Slow syncing avoids blocking by m.xsw.tw
4. **Persistent**: Queue survives server restarts
5. **Prioritized**: Popular books (high access count) sync first
6. **Observable**: Admin endpoints provide full visibility
7. **Flexible**: Configurable sync time and rate limits

## Monitoring

Use the stats endpoint to monitor:
- How many books are pending
- When the last sync ran
- How many completed/failed
- Current rate limit settings

Example monitoring query:
```bash
curl http://localhost:8000/xsw/api/admin/midnight-sync/stats
```

## See Also

- **[UNFINISHED_BOOKS_SYNC.md](UNFINISHED_BOOKS_SYNC.md)**: Detailed documentation about the automatic unfinished books sync feature
- **[BACKGROUND_JOBS.md](BACKGROUND_JOBS.md)**: Background job system documentation
- **[TWO_PHASE_LOADING.md](TWO_PHASE_LOADING.md)**: Two-phase loading strategy for better UX
