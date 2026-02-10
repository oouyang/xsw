#!/usr/bin/env bash
#
# sync_books.sh - Sync book metadata with rate limiting
#
# Reads book IDs from book_ids.txt and fetches metadata for each book
#
# Environment variables:
#   SLEEP_BETWEEN_CALLS   - Delay between requests in seconds (default: 3.0)
#   API_BASE              - API base URL (default: http://localhost:8000/xsw/api)
#   DATA_DIR              - Data storage directory (default: ./sync_data)
#   BATCH_SIZE            - Process books in batches (default: 50)
#   MAX_CONSECUTIVE_FAILS - Stop after N consecutive failures (default: 20)
#   RESUME_FROM_BOOK      - Resume from specific book ID (optional)
#

set -uo pipefail

# Configuration
SLEEP_BETWEEN_CALLS="${SLEEP_BETWEEN_CALLS:-3.0}"
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
DATA_DIR="${DATA_DIR:-./sync_data}"
BATCH_SIZE="${BATCH_SIZE:-50}"
MAX_CONSECUTIVE_FAILS="${MAX_CONSECUTIVE_FAILS:-20}"
RESUME_FROM_BOOK="${RESUME_FROM_BOOK:-}"

# Input/Output files
BOOK_IDS_FILE="${DATA_DIR}/book_ids.txt"
CHECKPOINT_FILE="${DATA_DIR}/books_checkpoint.txt"
FAILED_BOOKS_FILE="${DATA_DIR}/failed_books.txt"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[BOOKS]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[BOOKS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[BOOKS]${NC} $*"
}

log_error() {
    echo -e "${RED}[BOOKS]${NC} $*"
}

# Check if book IDs file exists
if [[ ! -f "$BOOK_IDS_FILE" ]]; then
    log_warning "Book IDs file not found: $BOOK_IDS_FILE"
    log_info "Run sync_categories.sh first to discover books"
    exit 1
fi

# Track statistics
total_books=0
successful_books=0
failed_books=0
skipped_books=0
consecutive_failures=0

# Fetch book metadata with retry
fetch_book_metadata() {
    local book_id=$1
    local output_file="${DATA_DIR}/book_${book_id}.json"
    local url="${API_BASE}/books/${book_id}"
    local retry=0
    local max_retries=3

    # Skip if already exists and is valid
    if [[ -f "$output_file" ]]; then
        local file_size=$(stat -f%z "$output_file" 2>/dev/null || stat -c%s "$output_file" 2>/dev/null || echo 0)
        if [[ $file_size -gt 100 ]]; then  # Reasonable JSON size
            if jq -e '.book_id' "$output_file" > /dev/null 2>&1; then
                skipped_books=$((skipped_books + 1))
                consecutive_failures=0  # Reset on successful skip
                return 0
            fi
        fi
    fi

    while [[ $retry -lt $max_retries ]]; do
        # Capture HTTP status code
        local http_code=$(curl -w "%{http_code}" -s -o "$output_file" "$url" 2>/dev/null)

        if [[ $http_code -eq 200 ]]; then
            # Validate JSON
            if jq -e '.book_id' "$output_file" > /dev/null 2>&1; then
                successful_books=$((successful_books + 1))
                consecutive_failures=0  # Reset on success
                local title=$(jq -r '.book_name // "Unknown"' "$output_file" 2>/dev/null)
                log_success "✓ Book $book_id: $title"
                return 0
            else
                log_warning "  Invalid JSON for book $book_id (HTTP $http_code)"
                rm -f "$output_file"
            fi
        else
            log_warning "  HTTP $http_code for book $book_id"
        fi

        retry=$((retry + 1))
        if [[ $retry -lt $max_retries ]]; then
            log_info "  Retry $retry/$max_retries for book $book_id..."
            sleep $((retry * 2))
        else
            failed_books=$((failed_books + 1))
            consecutive_failures=$((consecutive_failures + 1))
            log_error "  ✗ Failed after $max_retries retries: book $book_id (HTTP $http_code)"
            echo "$book_id" >> "$FAILED_BOOKS_FILE"
            rm -f "$output_file"
            return 1
        fi
    done
}

# Main sync loop
main() {
    total_books=$(wc -l < "$BOOK_IDS_FILE")

    log_info "Starting book metadata sync"
    log_info "Total books to sync:      $total_books"
    log_info "Rate limit:               ${SLEEP_BETWEEN_CALLS}s between requests"
    log_info "Batch size:               $BATCH_SIZE books"
    log_info "Max consecutive failures: $MAX_CONSECUTIVE_FAILS"

    # Check for resume
    if [[ -n "$RESUME_FROM_BOOK" ]]; then
        log_info "Resuming from book:       $RESUME_FROM_BOOK"
    elif [[ -f "$CHECKPOINT_FILE" ]]; then
        RESUME_FROM_BOOK=$(cat "$CHECKPOINT_FILE")
        log_info "Resuming from checkpoint: $RESUME_FROM_BOOK"
    fi

    echo ""

    local start_time=$(date +%s)
    local current_book=0
    local batch_start=1
    local should_skip=false

    # Determine if we should skip to resume point
    if [[ -n "$RESUME_FROM_BOOK" ]]; then
        should_skip=true
    fi

    while IFS= read -r book_id; do
        current_book=$((current_book + 1))

        # Skip until we reach resume point
        if [[ "$should_skip" == true ]]; then
            if [[ "$book_id" == "$RESUME_FROM_BOOK" ]]; then
                should_skip=false
                log_info "Resuming from this book..."
            else
                continue
            fi
        fi

        # Progress indicator (show stats every 10 books)
        if [[ $((current_book % 10)) -eq 0 ]]; then
            local progress=$((current_book * 100 / total_books))
            log_info "Progress: ${current_book}/${total_books} (${progress}%) - ✓${successful_books} ⊘${skipped_books} ✗${failed_books}"
        fi

        # Fetch book metadata (will handle its own errors)
        fetch_book_metadata "$book_id" || true

        # Check consecutive failures
        if [[ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILS ]]; then
            log_error ""
            log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_error "Maximum consecutive failures reached: $consecutive_failures"
            log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_error "Possible issues:"
            log_error "  - Backend service is down"
            log_error "  - Origin site is blocking requests"
            log_error "  - Network connectivity issues"
            log_error ""
            log_error "To resume from this point later, run:"
            log_error "  RESUME_FROM_BOOK=$book_id ./sync_books.sh"
            log_error ""
            echo "$book_id" > "$CHECKPOINT_FILE"
            exit 1
        fi

        # Save checkpoint every batch
        if [[ $((current_book % BATCH_SIZE)) -eq 0 ]]; then
            local batch_end=$current_book
            echo "$book_id" > "$CHECKPOINT_FILE"
            log_info "Batch checkpoint: books ${batch_start}-${batch_end} complete (checkpoint saved)"
            batch_start=$((batch_end + 1))
        fi

        # Rate limiting
        if [[ $current_book -lt $total_books ]]; then
            sleep "$SLEEP_BETWEEN_CALLS"
        fi

    done < "$BOOK_IDS_FILE"

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    # Summary
    echo ""
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "Book Metadata Sync Complete"
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Total books:          $total_books"
    log_info "Newly synced:         $successful_books"
    log_info "Skipped (cached):     $skipped_books"
    log_info "Failed:               $failed_books"
    log_info "Duration:             ${minutes}m ${seconds}s"
    log_info "Data saved to:        $DATA_DIR"

    # Clear checkpoint on successful completion
    if [[ -f "$CHECKPOINT_FILE" ]]; then
        rm -f "$CHECKPOINT_FILE"
        log_info "Checkpoint cleared"
    fi

    # Report failed books
    if [[ -f "$FAILED_BOOKS_FILE" ]] && [[ -s "$FAILED_BOOKS_FILE" ]]; then
        local failed_count=$(wc -l < "$FAILED_BOOKS_FILE")
        echo ""
        log_warning "Failed books logged to: $FAILED_BOOKS_FILE"
        log_warning "To retry failed books only:"
        log_warning "  cat $FAILED_BOOKS_FILE | while read id; do RESUME_FROM_BOOK=\$id ./sync_books.sh; done"
    fi

    echo ""
}

# Trap to save checkpoint on interrupt
trap 'log_warning "Sync interrupted! Checkpoint saved. Resume with: ./sync_books.sh"; exit 130' INT TERM

main "$@"
