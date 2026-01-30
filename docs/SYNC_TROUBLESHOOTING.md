# Sync Scripts Troubleshooting Guide

## Issue: sync_books.sh Exits After Individual Book Failures

### Problem Description

**Symptom**: Script exits with "Command exited with non-zero status 1" after a book fails:
```
[BOOKS] Progress: 150/2397 (6%)
[BOOKS] Batch checkpoint: books 101-150 complete
[BOOKS]   Retry 1/3 for book 1094355...
[BOOKS]   Retry 2/3 for book 1094355...
[BOOKS]   ✗ Failed after 3 retries: book 1094355
Command exited with non-zero status 1
```

**Root Cause**: The `set -e` flag caused the script to exit when `fetch_book_metadata()` returned a non-zero exit code.

### Solution (Fixed in Latest Version)

The script has been improved with:

1. **Removed `-e` flag** - Script no longer exits on individual failures
2. **Consecutive failure detection** - Stops only after 20+ consecutive failures
3. **Checkpoint/resume** - Auto-saves progress and resumes
4. **Failed books log** - Tracks failed book IDs for retry
5. **Better error reporting** - Shows HTTP status codes

### Using the Improved Script

#### Basic Usage
```bash
./sync_books.sh
```

The script will now:
- Continue past individual book failures
- Track consecutive failures (stops at 20)
- Save checkpoints every 50 books
- Log failed books to `sync_data/failed_books.txt`

#### Resume After Interruption
```bash
# Automatic resume from checkpoint
./sync_books.sh

# Or manually specify book ID
RESUME_FROM_BOOK=1094355 ./sync_books.sh
```

#### Adjust Failure Tolerance
```bash
# Allow more consecutive failures before stopping
MAX_CONSECUTIVE_FAILS=50 ./sync_books.sh

# Or be more strict
MAX_CONSECUTIVE_FAILS=10 ./sync_books.sh
```

#### Retry Only Failed Books
```bash
# After completion, retry books that failed
cat sync_data/failed_books.txt | while read book_id; do
  echo "Retrying book $book_id..."
  RESUME_FROM_BOOK=$book_id ./sync_books.sh
done
```

### Progress Monitoring

The script now shows detailed stats every 10 books:
```
[BOOKS] Progress: 150/2397 (6%) - ✓120 ⊘25 ✗5
```

- ✓ = Successfully synced
- ⊘ = Skipped (already cached)
- ✗ = Failed

### Consecutive Failure Detection

If the script encounters 20 consecutive failures, it will stop and show:
```
[BOOKS] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[BOOKS] Maximum consecutive failures reached: 20
[BOOKS] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[BOOKS] Possible issues:
[BOOKS]   - Backend service is down
[BOOKS]   - Origin site is blocking requests
[BOOKS]   - Network connectivity issues
[BOOKS]
[BOOKS] To resume from this point later, run:
[BOOKS]   RESUME_FROM_BOOK=1094355 ./sync_books.sh
```

### Common Issues and Solutions

#### Issue 1: Too Many Consecutive Failures

**Cause**: Backend service down, origin site blocking, or network issues

**Solution**:
```bash
# Check if backend is running
docker ps | grep xsw

# Check backend logs
docker logs xsw | tail -50

# Test backend manually
curl http://localhost:8000/xsw/api/books/1

# If origin site is blocking, increase delays
SLEEP_BETWEEN_CALLS=5.0 ./sync_books.sh
```

#### Issue 2: Specific Books Always Fail

**Cause**: Some books may not exist or have invalid data on origin site

**Solution**:
```bash
# Check failed books
cat sync_data/failed_books.txt

# Test specific book manually
curl http://localhost:8000/xsw/api/books/1094355

# Continue without failed books (they'll be skipped on resume)
./sync_books.sh
```

#### Issue 3: HTTP 404 Errors

**Cause**: Book IDs don't exist on origin site

**Solution**: These are expected - not all discovered book IDs are valid. The script continues past 404 errors.

```bash
# View HTTP status codes in logs
grep "HTTP" sync_data/logs/sync_*.log | sort | uniq -c

# Example output:
#   1245 HTTP 200  (success)
#     50 HTTP 404  (not found - expected)
#      5 HTTP 500  (server error)
```

#### Issue 4: HTTP 429 or 503 Errors

**Cause**: Rate limiting or origin site overload

**Solution**:
```bash
# Increase delays significantly
SLEEP_BETWEEN_CALLS=10.0 MAX_CONSECUTIVE_FAILS=50 ./sync_books.sh

# Or wait and resume later
# The script will auto-resume from last checkpoint
```

#### Issue 5: Invalid JSON Responses

**Cause**: Incomplete responses or HTML error pages

**Solution**: Script automatically validates JSON and retries. Invalid responses are skipped and logged.

```bash
# Find invalid JSON entries in logs
grep "Invalid JSON" sync_data/logs/sync_*.log
```

### Best Practices

1. **Let it run**: The script can handle failures gracefully now
2. **Monitor progress**: Check logs periodically
   ```bash
   tail -f sync_data/logs/sync_$(date +%Y%m%d).log
   ```
3. **Use screen/tmux**: For long-running syncs
   ```bash
   screen -S sync-books
   ./sync_books.sh
   # Detach: Ctrl+A, D
   # Reattach: screen -r sync-books
   ```
4. **Check backend logs**: If many consecutive failures occur
   ```bash
   docker logs xsw | grep ERROR
   ```
5. **Retry failed books**: After completion, retry books that failed
   ```bash
   cat sync_data/failed_books.txt | wc -l  # Count failed books
   # Then retry them
   ```

### Performance Tuning

#### Faster (More Risk)
```bash
SLEEP_BETWEEN_CALLS=1.0 BATCH_SIZE=100 ./sync_books.sh
```

#### Safer (Slower)
```bash
SLEEP_BETWEEN_CALLS=5.0 BATCH_SIZE=25 MAX_CONSECUTIVE_FAILS=10 ./sync_books.sh
```

#### Balanced (Recommended)
```bash
SLEEP_BETWEEN_CALLS=3.0 BATCH_SIZE=50 MAX_CONSECUTIVE_FAILS=20 ./sync_books.sh
```

### File Locations

- **Book metadata**: `sync_data/book_*.json`
- **Checkpoint**: `sync_data/books_checkpoint.txt`
- **Failed books**: `sync_data/failed_books.txt`
- **Logs**: `sync_data/logs/sync_YYYYMMDD.log`

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SLEEP_BETWEEN_CALLS` | 3.0 | Seconds between requests |
| `API_BASE` | http://localhost:8000/xsw/api | Backend API URL |
| `DATA_DIR` | ./sync_data | Data storage directory |
| `BATCH_SIZE` | 50 | Books per checkpoint |
| `MAX_CONSECUTIVE_FAILS` | 20 | Max failures before stopping |
| `RESUME_FROM_BOOK` | (none) | Book ID to resume from |

### Testing the Fix

To verify the script handles failures correctly:

```bash
# 1. Clean start
rm -f sync_data/books_checkpoint.txt sync_data/failed_books.txt

# 2. Run sync
./sync_books.sh

# 3. Observe behavior
# - Individual book failures don't stop the script
# - Progress is shown every 10 books
# - Checkpoints saved every 50 books
# - Failed books logged to failed_books.txt

# 4. Test resume
# Press Ctrl+C to interrupt, then:
./sync_books.sh
# Should resume from last checkpoint
```

### Migrating from Old Script

If you were using the old version and it stopped at book 1094355:

```bash
# Resume from where it failed
RESUME_FROM_BOOK=1094355 ./sync_books.sh

# Or let it auto-detect from checkpoint
./sync_books.sh
```

### Getting Help

If issues persist:

1. **Check backend logs**: `docker logs xsw | tail -100`
2. **Test API manually**: `curl http://localhost:8000/xsw/api/books/1`
3. **Review failed books**: `cat sync_data/failed_books.txt`
4. **Check consecutive failures**: Are they all the same error?
5. **Verify network**: Can you reach the origin site?

For the specific case of book 1094355 failing:
```bash
# Test if this book exists
curl -v http://localhost:8000/xsw/api/books/1094355

# Check backend logs for this book
docker logs xsw | grep 1094355

# Skip this book and continue
RESUME_FROM_BOOK=1094356 ./sync_books.sh
```

## Summary

The improved script is production-ready with:
- ✅ Continues past individual failures
- ✅ Tracks and stops on consecutive failures
- ✅ Automatic checkpoint/resume
- ✅ Detailed error reporting
- ✅ Failed books tracking for retry
- ✅ Graceful interrupt handling

Your sync will now complete successfully even if some individual books fail.
