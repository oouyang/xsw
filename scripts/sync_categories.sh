#!/usr/bin/env bash
#
# sync_categories.sh - Sync categories and discover books with rate limiting
#
# Discovers category slugs from /categories endpoint, then fetches book lists.
# czbooks.net uses slug-based categories (e.g. "xuanhuan", "dushi").
#
# Environment variables:
#   MAX_CATEGORIES        - Number of categories to sync (default: all discovered)
#   PAGES_PER_CATEGORY    - Pages per category (default: 10)
#   SLEEP_BETWEEN_CALLS   - Delay between requests in seconds (default: 2.0)
#   API_BASE              - API base URL (default: http://localhost:8000/xsw/api)
#   DATA_DIR              - Data storage directory (default: ./sync_data)
#

set -euo pipefail

# Configuration
MAX_CATEGORIES="${MAX_CATEGORIES:-0}"  # 0 = all discovered categories
PAGES_PER_CATEGORY="${PAGES_PER_CATEGORY:-10}"
SLEEP_BETWEEN_CALLS="${SLEEP_BETWEEN_CALLS:-2.0}"
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
DATA_DIR="${DATA_DIR:-./sync_data}"

# Create data directory
mkdir -p "$DATA_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[CATEGORIES]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[CATEGORIES]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[CATEGORIES]${NC} $*"
}

log_error() {
    echo -e "${RED}[CATEGORIES]${NC} $*"
}

# Track statistics
total_requests=0
successful_requests=0
failed_requests=0
total_books_discovered=0

# Discover categories from API
discover_categories() {
    local categories_file="${DATA_DIR}/categories.json"
    local url="${API_BASE}/categories"

    log_info "Discovering categories from ${url}..."

    if curl --fail -s -S -o "$categories_file" "$url" 2>/dev/null; then
        local count
        count=$(jq '. | length' "$categories_file" 2>/dev/null || echo 0)
        if [[ $count -gt 0 ]]; then
            log_success "Discovered $count categories"
            jq -r '.[] | "  - \(.id): \(.name)"' "$categories_file" 2>/dev/null
            return 0
        fi
    fi

    log_error "Failed to discover categories"
    rm -f "$categories_file"
    return 1
}

# Fetch category with retry logic
fetch_category_page() {
    local cat_slug=$1
    local cat_name=$2
    local page=$3
    local output_file="${DATA_DIR}/c_${cat_slug}_p${page}.json"
    local url="${API_BASE}/categories/${cat_slug}/books?page=${page}"
    local retry=0
    local max_retries=3

    while [[ $retry -lt $max_retries ]]; do
        total_requests=$((total_requests + 1))

        if curl --fail -s -S -o "$output_file" "$url" 2>/dev/null; then
            # Count books in response
            local book_count
            book_count=$(jq '. | length' "$output_file" 2>/dev/null || echo 0)

            if [[ $book_count -gt 0 ]]; then
                successful_requests=$((successful_requests + 1))
                total_books_discovered=$((total_books_discovered + book_count))
                log_success "✓ ${cat_name} (${cat_slug}) Page $page: ${book_count} books"
                return 0
            else
                log_info "  ${cat_name} Page $page: No books found (empty page)"
                rm -f "$output_file"  # Remove empty response
                return 0
            fi
        else
            retry=$((retry + 1))
            if [[ $retry -lt $max_retries ]]; then
                log_info "  Retry $retry/$max_retries for ${cat_slug} page $page..."
                sleep $((retry * 2))  # Exponential backoff
            else
                failed_requests=$((failed_requests + 1))
                log_warning "  ✗ Failed after $max_retries retries: ${cat_slug} page $page"
                rm -f "$output_file"  # Remove partial/failed response
                return 1
            fi
        fi
    done
}

# Main sync loop
main() {
    # Step 1: Discover categories
    if ! discover_categories; then
        exit 1
    fi

    local categories_file="${DATA_DIR}/categories.json"

    # Get category slugs and names
    local cat_slugs
    cat_slugs=$(jq -r '.[].id' "$categories_file" 2>/dev/null)
    local total_cats
    total_cats=$(echo "$cat_slugs" | wc -l)

    # Limit categories if MAX_CATEGORIES is set
    if [[ $MAX_CATEGORIES -gt 0 ]] && [[ $MAX_CATEGORIES -lt $total_cats ]]; then
        cat_slugs=$(echo "$cat_slugs" | head -n "$MAX_CATEGORIES")
        total_cats=$MAX_CATEGORIES
        log_info "Limiting to first $MAX_CATEGORIES categories"
    fi

    echo ""
    log_info "Starting category sync: $total_cats categories × $PAGES_PER_CATEGORY pages"
    log_info "Rate limit: ${SLEEP_BETWEEN_CALLS}s between requests"
    echo ""

    local start_time
    start_time=$(date +%s)
    local cat_index=0

    while IFS= read -r cat_slug; do
        cat_index=$((cat_index + 1))
        local cat_name
        cat_name=$(jq -r --arg slug "$cat_slug" '.[] | select(.id == $slug) | .name' "$categories_file" 2>/dev/null)
        log_info "Category $cat_index/$total_cats: $cat_name ($cat_slug)"

        for ((page=1; page<=PAGES_PER_CATEGORY; page++)); do
            fetch_category_page "$cat_slug" "$cat_name" "$page"

            # Rate limiting delay (except for last request)
            if [[ ! ($cat_index -eq $total_cats && $page -eq $PAGES_PER_CATEGORY) ]]; then
                sleep "$SLEEP_BETWEEN_CALLS"
            fi
        done

        echo ""  # Blank line between categories
    done <<< "$cat_slugs"

    local end_time
    end_time=$(date +%s)
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
    find "$DATA_DIR" -name "c_*_p*.json" -exec jq -r '.[].book_id' {} \; 2>/dev/null | sort -u > "$book_ids_file"
    local unique_books
    unique_books=$(wc -l < "$book_ids_file")
    log_info "Unique books:         $unique_books (saved to book_ids.txt)"
    echo ""
}

main "$@"
