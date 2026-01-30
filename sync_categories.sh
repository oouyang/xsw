#!/usr/bin/env bash
#
# sync_categories.sh - Sync categories and discover books with rate limiting
#
# Environment variables:
#   MAX_CATEGORIES        - Number of categories to sync (default: 7)
#   PAGES_PER_CATEGORY    - Pages per category (default: 10)
#   SLEEP_BETWEEN_CALLS   - Delay between requests in seconds (default: 2.0)
#   API_BASE              - API base URL (default: http://localhost:8000/xsw/api)
#   DATA_DIR              - Data storage directory (default: ./sync_data)
#

set -euo pipefail

# Configuration
MAX_CATEGORIES="${MAX_CATEGORIES:-9}"
PAGES_PER_CATEGORY="${PAGES_PER_CATEGORY:-10}"
SLEEP_BETWEEN_CALLS="${SLEEP_BETWEEN_CALLS:-2.0}"
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
DATA_DIR="${DATA_DIR:-./sync_data}"

# Create data directory
mkdir -p "$DATA_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[CATEGORIES]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[CATEGORIES]${NC} $*"
}

# Track statistics
total_requests=0
successful_requests=0
failed_requests=0
total_books_discovered=0

# Fetch category with retry logic
fetch_category_page() {
    local category=$1
    local page=$2
    local output_file="${DATA_DIR}/c${category}_p${page}.json"
    local url="${API_BASE}/categories/${category}/books?page=${page}"
    local retry=0
    local max_retries=3

    while [[ $retry -lt $max_retries ]]; do
        total_requests=$((total_requests + 1))

        if curl --fail -s -S -o "$output_file" "$url" 2>/dev/null; then
            # Count books in response
            local book_count=$(jq '. | length' "$output_file" 2>/dev/null || echo 0)

            if [[ $book_count -gt 0 ]]; then
                successful_requests=$((successful_requests + 1))
                total_books_discovered=$((total_books_discovered + book_count))
                log_success "✓ Category $category Page $page: ${book_count} books"
                return 0
            else
                log_info "  Category $category Page $page: No books found (empty page)"
                rm -f "$output_file"  # Remove empty response
                return 0
            fi
        else
            retry=$((retry + 1))
            if [[ $retry -lt $max_retries ]]; then
                log_info "  Retry $retry/$max_retries for category $category page $page..."
                sleep $((retry * 2))  # Exponential backoff
            else
                failed_requests=$((failed_requests + 1))
                log_info "  ✗ Failed after $max_retries retries: category $category page $page"
                rm -f "$output_file"  # Remove partial/failed response
                return 1
            fi
        fi
    done
}

# Main sync loop
main() {
    log_info "Starting category sync: $MAX_CATEGORIES categories × $PAGES_PER_CATEGORY pages"
    log_info "Rate limit: ${SLEEP_BETWEEN_CALLS}s between requests"
    echo ""

    local start_time=$(date +%s)

    for ((category=1; category<=MAX_CATEGORIES; category++)); do
        log_info "Category $category/$MAX_CATEGORIES:"

        for ((page=1; page<=PAGES_PER_CATEGORY; page++)); do
            fetch_category_page "$category" "$page"

            # Rate limiting delay (except for last request)
            if [[ ! ($category -eq $MAX_CATEGORIES && $page -eq $PAGES_PER_CATEGORY) ]]; then
                sleep "$SLEEP_BETWEEN_CALLS"
            fi
        done

        echo ""  # Blank line between categories
    done

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Summary
    echo ""
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "Category Sync Complete"
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Total requests:       $total_requests"
    log_info "Successful:           $successful_requests"
    log_info "Failed:               $failed_requests"
    log_info "Books discovered:     $total_books_discovered"
    log_info "Duration:             ${duration}s"
    log_info "Data saved to:        $DATA_DIR"
    echo ""

    # Extract all unique book IDs for next phase
    local book_ids_file="${DATA_DIR}/book_ids.txt"
    find "$DATA_DIR" -name "c*_p*.json" -exec jq -r '.[].book_id' {} \; 2>/dev/null | sort -u > "$book_ids_file"
    local unique_books=$(wc -l < "$book_ids_file")
    log_info "Unique books:         $unique_books (saved to book_ids.txt)"
    echo ""
}

main "$@"
