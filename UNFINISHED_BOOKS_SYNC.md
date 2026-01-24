# Automatic Sync for Unfinished Books

## Overview

This feature automatically syncs all unfinished books during the midnight sync process to check for new chapters and status updates.

## What It Does

The midnight sync scheduler now:
1. **Automatically adds all unfinished books to the sync queue** during each midnight sync
2. Checks the book's `status` field in the database
3. Books with `status != "已完成"` (not completed) are considered unfinished
4. Adds these books to the pending sync queue with priority 1

## How It Works

### Automatic Sync at Midnight

Every night at the configured time (default: midnight), the scheduler:

1. **Step 1: Enqueue Unfinished Books**
   - Queries all books from the database where `status != "已完成"`
   - For each unfinished book:
     - If already in queue: Resets status to "pending" (if was completed/failed)
     - If not in queue: Adds new entry with priority 1

2. **Step 2: Process Sync Queue**
   - Processes all pending books in priority order
   - Books with higher priority are synced first
   - Rate limiting applies (default: 5 seconds between books)

### Priority System

- **Priority 0**: User-accessed books (via `track_book_access()`)
- **Priority 1**: Automatically added unfinished books
- Higher priority = synced first

### Status Detection

The system checks the `Book.status` field:
- `"已完成"` = Completed (will NOT be synced automatically)
- Any other value = Unfinished (will be synced automatically)
- Common unfinished statuses: `"進行中"`, `"连载中"`, etc.

## Implementation Details

### Files Modified

1. **[midnight_sync.py](midnight_sync.py)**
   - Modified `_run_midnight_sync()` to enqueue unfinished books first
   - Added `enqueue_unfinished_books()` method for manual triggering

2. **[main_optimized.py](main_optimized.py)**
   - Added `/admin/midnight-sync/enqueue-unfinished` API endpoint

### Database Schema

Uses existing tables:
- **`books`** table: Contains `status` field
- **`pending_sync_queue`** table: Tracks books to sync

### Code Flow

```python
# During midnight sync
def _run_midnight_sync(self):
    # STEP 1: Add all unfinished books
    unfinished_books = session.query(Book).filter(Book.status != "已完成").all()

    for book in unfinished_books:
        if book_id in queue:
            # Reset if was completed/failed
            if status in ["completed", "failed"]:
                status = "pending"
                priority = 1
        else:
            # Add new entry
            queue.add(book_id, priority=1)

    # STEP 2: Process all pending books
    pending = queue.get_all_pending()
    for book in pending.order_by(priority.desc()):
        job_manager.enqueue_sync(book_id)
        sleep(rate_limit)
```

## API Endpoints

### 1. Get Sync Stats
```bash
GET /admin/midnight-sync/stats
```

Returns statistics about the sync queue including:
- Total books in queue
- Pending, syncing, completed, failed counts
- Last sync date
- Next sync time

**Example Response:**
```json
{
  "total": 150,
  "pending": 45,
  "syncing": 2,
  "completed": 98,
  "failed": 5,
  "last_sync_date": "2026-01-22T00:00:00",
  "next_sync_time": "00:00",
  "slow_rate_limit": 5.0
}
```

### 2. Manually Enqueue Unfinished Books
```bash
POST /admin/midnight-sync/enqueue-unfinished
```

Manually triggers the enqueuing of all unfinished books without waiting for midnight.

**Example Response:**
```json
{
  "status": "success",
  "added_count": 23,
  "message": "Added 23 unfinished books to sync queue"
}
```

**Use Cases:**
- Testing the feature
- Syncing unfinished books immediately after adding them
- Recovering from failed syncs

### 3. Trigger Full Midnight Sync
```bash
POST /admin/midnight-sync/trigger
```

Manually triggers the entire midnight sync process (enqueue + process).

**Example Response:**
```json
{
  "status": "triggered",
  "message": "Midnight sync started in background"
}
```

### 4. Clear Completed Entries
```bash
POST /admin/midnight-sync/clear-completed
```

Clears completed and failed entries from the sync queue.

**Example Response:**
```json
{
  "status": "cleared",
  "count": 98,
  "message": "Cleared 98 completed/failed entries"
}
```

## Configuration

Set via environment variables in [.env](.env):

```bash
# Midnight sync configuration
MIDNIGHT_SYNC_HOUR=0          # Hour to run sync (0-23)
MIDNIGHT_SYNC_MINUTE=0        # Minute to run sync (0-59)
MIDNIGHT_SYNC_RATE_LIMIT=5.0  # Seconds between each book sync
```

**Default Values:**
- Sync time: 00:00 (midnight)
- Rate limit: 5 seconds between books

## Benefits

### 1. Automatic Updates
- No manual intervention needed
- All ongoing books stay up-to-date
- New chapters are detected automatically

### 2. Smart Priority
- User-accessed books (priority 0) sync before automatic books (priority 1)
- Most frequently accessed books sync first
- Ensures user experience is prioritized

### 3. Status-Aware
- Only syncs books that need updates
- Completed books are not synced repeatedly
- Saves bandwidth and processing time

### 4. Rate Limited
- Slow syncing (default: 5 seconds between books)
- Avoids being blocked by source website
- Background operation doesn't affect user experience

### 5. Resumable
- If sync is interrupted, unfinished books are tracked
- Next sync will pick up where it left off
- Failed syncs can be retried

## Usage Examples

### Example 1: Checking Sync Status

```bash
# Check current sync queue status
curl http://localhost:8000/admin/midnight-sync/stats

# Output:
{
  "total": 150,
  "pending": 45,
  "syncing": 2,
  "completed": 98,
  "failed": 5,
  "last_sync_date": "2026-01-22T00:00:00",
  "next_sync_time": "00:00"
}
```

**Interpretation:**
- 150 total books in queue
- 45 waiting to be synced
- 2 currently syncing
- 98 successfully synced
- 5 failed (can be retried)

### Example 2: Manually Triggering Sync for Unfinished Books

```bash
# Add all unfinished books to queue immediately
curl -X POST http://localhost:8000/admin/midnight-sync/enqueue-unfinished

# Output:
{
  "status": "success",
  "added_count": 23,
  "message": "Added 23 unfinished books to sync queue"
}
```

**When to use:**
- Just added new books to database
- Want to test the feature
- Need immediate sync without waiting for midnight

### Example 3: Full Sync Process

```bash
# Trigger full midnight sync immediately
curl -X POST http://localhost:8000/admin/midnight-sync/trigger

# Output:
{
  "status": "triggered",
  "message": "Midnight sync started in background"
}

# Check progress
curl http://localhost:8000/admin/midnight-sync/stats
```

### Example 4: Cleaning Up Queue

```bash
# Clear completed/failed entries to reduce clutter
curl -X POST http://localhost:8000/admin/midnight-sync/clear-completed

# Output:
{
  "status": "cleared",
  "count": 98,
  "message": "Cleared 98 completed/failed entries"
}
```

## Logging

The system logs all operations for debugging:

```
[MidnightSync] Step 1: Adding all unfinished books to sync queue
[MidnightSync] Found 23 unfinished books
[MidnightSync] Added unfinished book to queue: book123
[MidnightSync] Reset status for unfinished book: book456
[MidnightSync] Enqueued 15 new unfinished books for sync
[MidnightSync] Step 2: Processing pending sync queue
[MidnightSync] Found 45 books to sync
[MidnightSync] Syncing book 1/45: book123 (accessed 5 times)
[MidnightSync] Queued sync for book123
[MidnightSync] Waiting 5.0s before next book...
```

**Log Levels:**
- `INFO`: Major events (sync started, completed, books added)
- `DEBUG`: Detailed operations (individual book processing)
- `ERROR`: Failures and exceptions

## Performance Considerations

### Rate Limiting

With default settings (5s between books):
- 23 books = ~115 seconds (~2 minutes)
- 100 books = ~500 seconds (~8 minutes)
- 500 books = ~2500 seconds (~42 minutes)

**Recommendation:** Keep rate limit at 5 seconds or higher to avoid being blocked.

### Database Load

- Query is efficient: single `SELECT * FROM books WHERE status != '已完成'`
- Index on `status` field recommended for large databases
- Queue operations use indexed lookups

### Background Processing

- Sync runs in background thread
- Does not block API requests
- User experience is not affected

## Troubleshooting

### Issue: Books Not Being Synced

**Check:**
1. Is midnight scheduler running?
   ```bash
   curl http://localhost:8000/admin/midnight-sync/stats
   ```
2. Are books in the database with `status != "已完成"`?
3. Check logs for errors

### Issue: Too Many Books in Queue

**Solution:**
```bash
# Clear completed entries
curl -X POST http://localhost:8000/admin/midnight-sync/clear-completed
```

### Issue: Sync Taking Too Long

**Options:**
1. Increase `MIDNIGHT_SYNC_RATE_LIMIT` (faster, but risk being blocked)
2. Reduce number of books by marking completed ones
3. Run sync earlier in the day

### Issue: Books Marked as Failed

**Check:**
- Network connectivity
- Source website availability
- Rate limiting

**Retry:**
```bash
# Trigger sync again (will retry failed books)
curl -X POST http://localhost:8000/admin/midnight-sync/trigger
```

## Future Enhancements

Potential improvements:

1. **Configurable Status Values**: Allow customizing which statuses are considered "unfinished"
2. **Sync Frequency**: Different sync frequencies for different book priorities
3. **Smart Scheduling**: Sync popular books more frequently
4. **Batch Operations**: Process multiple books in parallel (with rate limiting)
5. **Status Change Detection**: Alert when book status changes from "進行中" to "已完成"
6. **Chapter Count Tracking**: Only sync if expected chapter count changed

## Summary

This feature provides automatic, hands-off syncing of all unfinished books in the database:

✅ **Automatic**: Runs at midnight without manual intervention
✅ **Smart**: Only syncs unfinished books
✅ **Prioritized**: User-accessed books sync first
✅ **Rate Limited**: Avoids being blocked by source
✅ **Resumable**: Handles failures gracefully
✅ **Transparent**: Full logging and statistics
✅ **Controllable**: Manual API endpoints for testing/control

The midnight sync scheduler now ensures all ongoing books stay up-to-date automatically!
