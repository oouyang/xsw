# Unfinished Books Sync Flow

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    MIDNIGHT SYNC TRIGGER                        │
│                     (Every night at 00:00)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  STEP 1: Query All Unfinished Books        │
        │  SELECT * FROM books                       │
        │  WHERE status != '已完成'                   │
        └────────────────────┬───────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  Found N Unfinished Books                  │
        │  Examples:                                 │
        │  - Book A (status: "進行中")                │
        │  - Book B (status: "连载中")                │
        │  - Book C (status: "updating")             │
        └────────────────────┬───────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  For Each Unfinished Book:                 │
        │  ┌──────────────────────────────────────┐  │
        │  │ Already in Queue?                    │  │
        │  │  YES → Reset to "pending" (priority 1)│ │
        │  │  NO  → Add new entry (priority 1)    │  │
        │  └──────────────────────────────────────┘  │
        └────────────────────┬───────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  STEP 2: Process Pending Sync Queue        │
        │  SELECT * FROM pending_sync_queue          │
        │  WHERE sync_status = 'pending'             │
        │  ORDER BY priority DESC, access_count DESC │
        └────────────────────┬───────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  Priority-Based Processing:                │
        │                                            │
        │  Priority 0 (User-accessed books)          │
        │  ├─ Book X (accessed 10 times)             │
        │  ├─ Book Y (accessed 5 times)              │
        │  └─ Book Z (accessed 2 times)              │
        │                                            │
        │  Priority 1 (Auto-added unfinished books)  │
        │  ├─ Book A (accessed 3 times)              │
        │  ├─ Book B (accessed 1 time)               │
        │  └─ Book C (accessed 1 time)               │
        └────────────────────┬───────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  For Each Book in Queue:                   │
        │  ┌──────────────────────────────────────┐  │
        │  │ 1. Update status to "syncing"        │  │
        │  │ 2. Enqueue background job            │  │
        │  │ 3. Wait 5 seconds (rate limit)       │  │
        │  │ 4. Update status to "completed"      │  │
        │  └──────────────────────────────────────┘  │
        └────────────────────┬───────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  Background Jobs Process Books:            │
        │  - Fetch book info from source             │
        │  - Fetch all chapters                      │
        │  - Update database                         │
        │  - Cache content                           │
        └────────────────────┬───────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │  COMPLETE                                  │
        │  - All unfinished books synced             │
        │  - User-accessed books synced              │
        │  - Status updated to "completed"           │
        └────────────────────────────────────────────┘
```

## Timeline Example

**Scenario:** 5 user-accessed books + 3 unfinished books

```
Time: 00:00:00  → Midnight sync triggered
Time: 00:00:01  → Query unfinished books
Time: 00:00:02  → Found 3 unfinished books (A, B, C)
Time: 00:00:03  → Add Book A to queue (priority 1)
Time: 00:00:04  → Add Book B to queue (priority 1)
Time: 00:00:05  → Add Book C to queue (priority 1)
Time: 00:00:06  → Query pending books: 8 total (5 user + 3 auto)
Time: 00:00:07  → Start syncing Book X (priority 0, accessed 10x)
Time: 00:00:12  → Start syncing Book Y (priority 0, accessed 5x)
Time: 00:00:17  → Start syncing Book Z (priority 0, accessed 2x)
Time: 00:00:22  → Start syncing Book A (priority 1, accessed 3x)
Time: 00:00:27  → Start syncing Book B (priority 1, accessed 1x)
Time: 00:00:32  → Start syncing Book C (priority 1, accessed 1x)
Time: 00:00:37  → All books synced
Time: 00:00:38  → Midnight sync complete
```

**Total Time:** 38 seconds for 8 books

## Priority Queue Visualization

```
┌──────────────────────────────────────────────────┐
│         PENDING SYNC QUEUE                       │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌────────────────────────────────────────┐     │
│  │  PRIORITY 0 (User-Accessed)            │     │
│  │  ✓ Accessed by users today             │     │
│  │  ✓ Synced FIRST                        │     │
│  ├────────────────────────────────────────┤     │
│  │  • Book X (10 accesses) ← Sync 1st     │     │
│  │  • Book Y (5 accesses)  ← Sync 2nd     │     │
│  │  • Book Z (2 accesses)  ← Sync 3rd     │     │
│  └────────────────────────────────────────┘     │
│                                                  │
│  ┌────────────────────────────────────────┐     │
│  │  PRIORITY 1 (Auto-Added Unfinished)    │     │
│  │  ✓ status != "已完成"                   │     │
│  │  ✓ Synced AFTER user books             │     │
│  ├────────────────────────────────────────┤     │
│  │  • Book A (3 accesses)  ← Sync 4th     │     │
│  │  • Book B (1 access)    ← Sync 5th     │     │
│  │  • Book C (1 access)    ← Sync 6th     │     │
│  └────────────────────────────────────────┘     │
│                                                  │
└──────────────────────────────────────────────────┘
```

## Status Transitions

```
Book Status in Database:
┌────────────┐
│ 進行中      │  ──┐
└────────────┘    │
┌────────────┐    │
│ 连载中      │  ──┤  All These
└────────────┘    │  Are Synced
┌────────────┐    │  Automatically
│ updating    │  ──┤
└────────────┘    │
┌────────────┐    │
│ ongoing     │  ──┘
└────────────┘

┌────────────┐
│ 已完成      │  ──→  NOT Synced
└────────────┘       (Already Complete)
```

## Sync Queue Status Flow

```
Book in Queue Status:

┌─────────┐    Midnight Sync     ┌─────────┐
│         │    Adds Book         │         │
│  (none) │ ──────────────────→  │ pending │
│         │                      │         │
└─────────┘                      └────┬────┘
                                      │
                    Worker Picks Up   │
                    ┌─────────────────┘
                    │
                    ▼
              ┌──────────┐    Job       ┌───────────┐
              │          │    Succeeds   │           │
              │ syncing  │ ────────────→ │ completed │
              │          │               │           │
              └────┬─────┘               └───────────┘
                   │
                   │ Job Fails
                   ▼
              ┌─────────┐
              │         │
              │ failed  │  (Can be retried)
              │         │
              └─────────┘
```

## Database Query Examples

**Find all unfinished books:**
```sql
SELECT id, name, status
FROM books
WHERE status != '已完成'
ORDER BY last_scraped_at DESC;
```

**Check queue status:**
```sql
SELECT
  book_id,
  priority,
  access_count,
  sync_status,
  accessed_at
FROM pending_sync_queue
WHERE sync_status = 'pending'
ORDER BY priority DESC, access_count DESC;
```

**Count by status:**
```sql
SELECT status, COUNT(*) as count
FROM books
GROUP BY status;
```

**Example Results:**
```
status      | count
------------|------
進行中       | 23
已完成       | 127
连载中       | 15
```

## Rate Limiting Visualization

```
Time ──────────────────────────────────────────────→

Book 1 [████████] (sync)
                 ⏱️ (5s wait)
                           Book 2 [████████] (sync)
                                          ⏱️ (5s wait)
                                                    Book 3 [████████] (sync)

Legend:
[████████] = Book sync operation (~2-3 seconds)
⏱️         = Rate limit delay (5 seconds)
```

**Why 5 seconds?**
- Prevents overwhelming the source website
- Avoids rate limiting/blocking
- Background operation, no user impact
- Can be configured via `MIDNIGHT_SYNC_RATE_LIMIT`

## Summary

This flow ensures:
1. ✅ All unfinished books are automatically discovered
2. ✅ User-accessed books are prioritized
3. ✅ Rate limiting prevents blocking
4. ✅ Completed books are not re-synced
5. ✅ Full observability via logs and API
