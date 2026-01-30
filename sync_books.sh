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
#

set -euo pipefail

# Configuration
SLEEP_BETWEEN_CALLS="${SLEEP_BETWEEN_CALLS:-3.0}"
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
DATA_DIR="${DATA_DIR:-./sync_data}"
BATCH_SIZE="${BATCH_SIZE:-50}"

# Input/Output files
BOOK_IDS_FILE="${DATA_DIR}/book_ids.txt"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

# Fetch book metadata with retry
fetch_book_metadata() {
    local book_id=$1
    local output_file="${DATA_DIR}/book_${book_id}.json"
    local url="${API_BASE}/books/${book_id}"
    local retry=0
    local max_retries=3

    # Skip if already exists
    if [[ -f "$output_file" ]]; then
        local file_size=$(stat -f%z "$output_file" 2>/dev/null || stat -c%s "$output_file" 2>/dev/null || echo 0)
        if [[ $file_size -gt 100 ]]; then  # Reasonable JSON size
            skipped_books=$((skipped_books + 1))
            return 0
        fi
    fi

    while [[ $retry -lt $max_retries ]]; do
        if curl --fail -s -S -o "$output_file" "$url" 2>/dev/null; then
            # Validate JSON
            if jq -e '.book_id' "$output_file" > /dev/null 2>&1; then
                successful_books=$((successful_books + 1))
                local title=$(jq -r '.book_name // "Unknown"' "$output_file" 2>/dev/null)
                log_success "✓ Book $book_id: $title"
                return 0
            else
                log_warning "  Invalid JSON for book $book_id"
                rm -f "$output_file"
            fi
        fi

        retry=$((retry + 1))
        if [[ $retry -lt $max_retries ]]; then
            log_info "  Retry $retry/$max_retries for book $book_id..."
            sleep $((retry * 2))
        else
            failed_books=$((failed_books + 1))
            log_info "  ✗ Failed after $max_retries retries: book $book_id"
            rm -f "$output_file"
            return 1
        fi
    done
}

# Main sync loop
main() {
    total_books=$(wc -l < "$BOOK_IDS_FILE")

    log_info "Starting book metadata sync"
    log_info "Total books to sync:  $total_books"
    log_info "Rate limit:           ${SLEEP_BETWEEN_CALLS}s between requests"
    log_info "Batch size:           $BATCH_SIZE books"
    echo ""

    local start_time=$(date +%s)
    local current_book=0
    local batch_start=1

    while IFS= read -r book_id; do
        current_book=$((current_book + 1))

        # Progress indicator
        if [[ $((current_book % 10)) -eq 0 ]]; then
            local progress=$((current_book * 100 / total_books))
            log_info "Progress: ${current_book}/${total_books} (${progress}%)"
        fi

        fetch_book_metadata "$book_id"

        # Rate limiting
        if [[ $current_book -lt $total_books ]]; then
            sleep "$SLEEP_BETWEEN_CALLS"
        fi

        # Batch checkpoint
        if [[ $((current_book % BATCH_SIZE)) -eq 0 ]]; then
            local batch_end=$current_book
            log_info "Batch checkpoint: books ${batch_start}-${batch_end} complete"
            batch_start=$((batch_end + 1))
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
    echo ""
}

main "$@"
