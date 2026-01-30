# Whole Site Sync Plan

This document describes the comprehensive strategy for syncing the entire m.xsw.tw site while avoiding rate limiting and blocks.

## Overview

The sync process is divided into **4 phases**, each with increasingly conservative rate limiting to minimize the risk of being blocked by the origin site.

```
┌─────────────────────────────────────────────────────────────┐
│                   SYNC ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Phase 1: Categories & Discovery                            │
│  └─> Discover all books from category pages                 │
│       Rate: 2s between requests (~30 req/min)               │
│       Volume: ~70 requests (7 categories × 10 pages)        │
│                                                               │
│  Phase 2: Book Metadata                                      │
│  └─> Fetch detailed info for each discovered book           │
│       Rate: 3s between requests (~20 req/min)               │
│       Volume: Variable (~500-1000 books)                     │
│                                                               │
│  Phase 3: Chapter Lists                                      │
│  └─> Get chapter lists for all books                        │
│       Rate: 3s between requests (~20 req/min)               │
│       Volume: Same as Phase 2 (one per book)                │
│                                                               │
│  Phase 4: Chapter Content                                    │
│  └─> Fetch actual chapter text (MOST INTENSIVE)             │
│       Rate: 5s between requests (~12 req/min)               │
│       Volume: HUGE (~50,000-200,000 chapters)               │
│       Adaptive: Auto-adjust delay based on response times    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Rate Limiting Strategy

### Why Rate Limiting is Critical

The origin site (m.xsw.tw) will block IPs that make too many requests. Our backend already has rate limiting (`RATE_LIMIT_ENABLED=true`), but we need additional client-side throttling for large-scale syncs.

### Rate Limit Profiles

The sync system supports 3 profiles:

| Profile | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Risk | Speed |
|---------|---------|---------|---------|---------|------|-------|
| **Fast** | 0.5s | 1.0s | 1.0s | 2.0s | High | Fast |
| **Slow** (Default) | 2.0s | 3.0s | 3.0s | 5.0s | Low | Moderate |
| **Ultra-Slow** | 5.0s | 10.0s | 10.0s | 15.0s | Very Low | Slow |

**Recommendation**: Start with `--slow` (default). If you encounter blocking, switch to `--ultra-slow`.

### Adaptive Rate Limiting

Phase 4 (Chapter Content) implements adaptive rate limiting:

- **Monitors response times**: If responses are slow (>3s), it automatically increases delay
- **Adjusts dynamically**: Fast responses (< 0.5s) slightly decrease delay
- **Caps limits**: Delay stays between 1s and 30s
- **Failure detection**: If 30s delay is reached, the system warns that blocking may be occurring

## Execution Plan

### Quick Start

```bash
# Make scripts executable
chmod +x sync_*.sh

# Run full sync with default (slow) profile
./sync_full.sh --slow

# Run full sync with ultra-slow profile (safest)
./sync_full.sh --ultra-slow --categories 7 --pages 10

# Dry run to see what would be synced
./sync_full.sh --dry-run
```

### Step-by-Step Manual Execution

If you prefer to run phases individually:

```bash
# Phase 1: Categories (discover books)
MAX_CATEGORIES=7 PAGES_PER_CATEGORY=10 SLEEP_BETWEEN_CALLS=2.0 \
  ./sync_categories.sh

# Phase 2: Book metadata
SLEEP_BETWEEN_CALLS=3.0 \
  ./sync_books.sh

# Phase 3: Chapter lists
SLEEP_BETWEEN_CALLS=3.0 \
  ./sync_chapters_enhanced.sh

# Phase 4: Chapter content (intensive!)
SLEEP_BETWEEN_CALLS=5.0 \
  ./sync_content_enhanced.sh
```

## Volume Estimates

### Conservative Estimates (7 categories, 10 pages each)

| Phase | Requests | Time (Slow) | Time (Ultra-Slow) |
|-------|----------|-------------|-------------------|
| **Phase 1** | ~70 | 2-3 minutes | 6-8 minutes |
| **Phase 2** | ~700 | 35-40 minutes | 2 hours |
| **Phase 3** | ~700 | 35-40 minutes | 2 hours |
| **Phase 4** | ~70,000+ | **3-4 days** | **8-10 days** |

### Full Site Estimates (all categories, all pages)

Assuming:
- 20 categories
- 50 pages per category
- Average 15 books per page = 15,000 books
- Average 1,000 chapters per book = 15,000,000 chapters

| Phase | Requests | Time (Slow) | Time (Ultra-Slow) |
|-------|----------|-------------|-------------------|
| **Phase 1** | 1,000 | 30-40 minutes | 1.5 hours |
| **Phase 2** | 15,000 | 12-15 hours | 42 hours (1.75 days) |
| **Phase 3** | 15,000 | 12-15 hours | 42 hours (1.75 days) |
| **Phase 4** | 15,000,000 | **~3 years** | **~8 years** |

**Reality Check**: Phase 4 for the full site is **impractical**. Focus on:
1. Popular categories only
2. Recent/updated books only
3. Incremental syncing (new chapters only)

## Safety Features

### 1. Checkpoint & Resume

The system automatically saves progress:

```bash
# If sync is interrupted (Ctrl+C), resume with:
./sync_full.sh --resume
```

Checkpoints are saved:
- Every 100 chapters in Phase 4
- At the end of each phase
- On interrupt (Ctrl+C)

### 2. Retry Logic

All requests include retry logic:
- **3 retries** with exponential backoff (2s, 4s, 8s)
- Failed requests logged but don't stop the sync
- Consecutive failure threshold (default: 10) stops sync to prevent wasted effort

### 3. Validation

All responses are validated before being saved:
- JSON must be valid
- Required fields must exist
- Content length must be reasonable (chapters > 50 chars)
- Invalid responses are deleted and retried

### 4. Progress Tracking

Real-time progress indicators:
```
[CONTENT] Progress: 1500/70000 (2%) - 12.5 chapters/min
[CONTENT] Stats: ✓1450 ⊘45 ✗5 - Delay: 5.2s
```

- ✓ Newly synced
- ⊘ Skipped (already cached)
- ✗ Failed
- Delay: Current adaptive delay

## Data Organization

All synced data is stored in `./sync_data/`:

```
sync_data/
├── c1_p1.json                      # Category 1, Page 1
├── c1_p2.json                      # Category 1, Page 2
├── ...
├── book_ids.txt                    # All discovered book IDs
├── book_123.json                   # Book 123 metadata
├── book_123_chapters.json          # Book 123 chapter list
├── content_123_1.json              # Book 123, Chapter 1
├── content_123_2.json              # Book 123, Chapter 2
├── ...
├── content_sync_checkpoint.txt     # Resume checkpoint
├── content_sync_progress.txt       # Progress stats
├── chapter_inventory.txt           # Summary of all books/chapters
└── logs/
    ├── sync_20260129.log           # Daily log
    └── sync_report_20260129_140530.txt  # Final report
```

## Database Integration

The sync scripts fetch data through the API, which automatically:
1. **Caches to memory** (TTL: 15 minutes)
2. **Stores to database** (SQLite: persistent)
3. **Falls back to web scraping** (if cache miss)

This means:
- **First sync**: Slow (scrapes from source)
- **Subsequent syncs**: Fast (reads from database)
- **Updates**: Incremental (only new/changed content)

## Monitoring & Logs

### Live Monitoring

```bash
# Watch progress in real-time
tail -f sync_data/logs/sync_$(date +%Y%m%d).log

# Check current progress
cat sync_data/content_sync_progress.txt
```

### Log Analysis

```bash
# Count successful syncs
grep "✓" sync_data/logs/sync_*.log | wc -l

# Count failures
grep "✗" sync_data/logs/sync_*.log | wc -l

# Find errors
grep "ERROR" sync_data/logs/sync_*.log
```

## Troubleshooting

### Issue: "Connection refused"

**Cause**: Backend is not running

**Solution**:
```bash
# Start the backend
docker-compose up -d xsw
# Or locally:
uvicorn main_optimized:app --port 8000
```

### Issue: "Too many consecutive failures"

**Cause**: Site is rate limiting or blocking

**Solutions**:
1. **Increase delay**:
   ```bash
   ./sync_full.sh --ultra-slow
   ```

2. **Wait and resume**:
   ```bash
   # Wait 1 hour, then:
   ./sync_full.sh --resume --ultra-slow
   ```

3. **Check if IP is blocked**:
   ```bash
   curl https://m.xsw.tw/
   ```

### Issue: "Invalid JSON"

**Cause**: Incomplete or corrupted responses

**Solution**: The sync automatically retries and cleans up invalid files. If persistent:
```bash
# Find and remove invalid files
find sync_data -name "*.json" -size 0 -delete
find sync_data -name "*.json" -exec sh -c 'jq empty {} || rm {}' \;
```

### Issue: Sync is too slow

**Cause**: Rate limiting delays are too conservative

**Options**:
1. **Use faster profile** (risky):
   ```bash
   ./sync_full.sh --fast
   ```

2. **Parallelize** (advanced, DANGEROUS):
   ```bash
   # Split book list into chunks
   split -l 100 sync_data/book_ids.txt sync_data/batch_

   # Run multiple instances (different terminals)
   DATA_DIR=sync_data/batch1 ./sync_books.sh < sync_data/batch_aa
   DATA_DIR=sync_data/batch2 ./sync_books.sh < sync_data/batch_ab
   # ... etc

   # CAUTION: This increases blocking risk significantly!
   ```

3. **Focus on subset**:
   ```bash
   # Only sync 3 categories instead of all
   ./sync_full.sh --categories 3 --pages 5
   ```

## Best Practices

### 1. Start Small

```bash
# Test with minimal scope first
./sync_full.sh --categories 1 --pages 2 --slow

# If successful, scale up
./sync_full.sh --categories 7 --pages 10 --slow
```

### 2. Run During Off-Peak Hours

- Sync at night (local time) when site traffic is lower
- Less chance of competing with legitimate users
- Site may have higher rate limits during off-peak

### 3. Use Screen/Tmux

Phase 4 can take days. Use screen/tmux to keep running:

```bash
# Start screen session
screen -S xsw-sync

# Run sync
./sync_full.sh --ultra-slow

# Detach: Ctrl+A, D
# Reattach later: screen -r xsw-sync
```

### 4. Monitor Database Growth

```bash
# Check database size
du -h xsw_cache.db

# Check row counts
sqlite3 xsw_cache.db "SELECT COUNT(*) FROM chapters;"
sqlite3 xsw_cache.db "SELECT COUNT(*) FROM books;"
```

### 5. Backup Before Large Syncs

```bash
# Backup database
cp xsw_cache.db xsw_cache.db.backup_$(date +%Y%m%d)

# Backup sync data
tar czf sync_data_backup_$(date +%Y%m%d).tar.gz sync_data/
```

## Incremental Sync Strategy

Instead of syncing everything, focus on **incremental updates**:

### Daily Incremental Sync

1. **Use existing admin endpoints**:
   ```bash
   # Trigger midnight sync for tracked books
   curl -X POST http://localhost:8000/xsw/api/admin/midnight-sync/trigger
   ```

2. **Background jobs** handle incremental updates automatically
   - Syncs unfinished books nightly
   - Updates at slower rate (configured in `.env`)

### Selective Sync

```bash
# Sync specific books only
cat > sync_data/book_ids.txt <<EOF
123456
789012
345678
EOF

# Run phases 2-4 for these books only
./sync_books.sh
./sync_chapters_enhanced.sh
./sync_content_enhanced.sh
```

## Performance Optimization

### 1. Parallel Backend Workers

Increase backend job workers:
```bash
# .env
BG_JOB_WORKERS=4  # Default: 2
```

### 2. Database Indexing

```sql
-- Ensure indexes exist
CREATE INDEX IF NOT EXISTS idx_books_book_id ON books(book_id);
CREATE INDEX IF NOT EXISTS idx_chapters_book_id ON chapters(book_id);
CREATE INDEX IF NOT EXISTS idx_chapters_chapter_number ON chapters(chapter_number);
```

### 3. Memory Cache Settings

```bash
# .env
CACHE_TTL_SECONDS=3600    # 1 hour (default: 900)
CACHE_MAX_ITEMS=2000      # Default: 500
```

## Legal & Ethical Considerations

⚠️ **Important**:

1. **Respect Rate Limits**: The scripts implement conservative delays to avoid overwhelming the source site
2. **Fair Use**: Only sync what you need, when you need it
3. **Personal Use**: This tool is for personal/educational use only
4. **No Redistribution**: Do not redistribute scraped content
5. **Terms of Service**: Ensure compliance with the source site's ToS

## Summary

### Recommended Workflow

For a **balanced sync** (7 categories, good coverage, low risk):

```bash
# 1. Dry run to estimate
./sync_full.sh --dry-run --categories 7 --pages 10

# 2. Run actual sync with safe profile
./sync_full.sh --slow --categories 7 --pages 10

# 3. If interrupted, resume
./sync_full.sh --resume

# 4. Check results
cat sync_data/logs/sync_report_*.txt
```

### Key Takeaways

- ✅ **Use `--slow` profile** by default
- ✅ **Start with small scope** (1-2 categories) to test
- ✅ **Phase 4 takes days** for large volumes
- ✅ **Checkpoint/resume** works reliably
- ✅ **Adaptive rate limiting** helps avoid blocks
- ⚠️ **Full site sync is impractical** - focus on subsets
- ⚠️ **Use incremental syncing** for ongoing updates

### Support

For issues or questions:
- Check logs: `sync_data/logs/`
- Read this guide: `docs/SYNC_PLAN.md`
- Review backend logs: `docker logs xsw`
