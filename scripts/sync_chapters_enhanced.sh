#!/usr/bin/env bash
#
# sync_chapters_enhanced.sh - Sync chapter lists for all books with rate limiting
#
# Reads book metadata files and fetches chapter lists
#
# Environment variables:
#   SLEEP_BETWEEN_CALLS   - Delay between requests in seconds (default: 3.0)
#   API_BASE              - API base URL (default: http://localhost:8000/xsw/api)
#   DATA_DIR              - Data storage directory (default: ./sync_data)
#

set -euo pipefail

# Configuration
SLEEP_BETWEEN_CALLS="${SLEEP_BETWEEN_CALLS:-3.0}"
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
DATA_DIR="${DATA_DIR:-./sync_data}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[CHAPTERS]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[CHAPTERS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[CHAPTERS]${NC} $*"
}

# Track statistics
total_books=0
successful_books=0
failed_books=0
skipped_books=0
total_chapters=0

# Fetch chapter list for a book
fetch_chapter_list() {
    local book_file=$1
    local book_id=$(jq -r '.book_id' "$book_file" 2>/dev/null)
    local book_name=$(jq -r '.book_name // "Unknown"' "$book_file" 2>/dev/null)
    local output_file="${DATA_DIR}/book_${book_id}_chapters.json"
    local url="${API_BASE}/books/${book_id}/chapters?all=true"
    local retry=0
    local max_retries=3

    # Skip if already exists and is valid
    if [[ -f "$output_file" ]]; then
        if jq -e '. | length' "$output_file" > /dev/null 2>&1; then
            local chapter_count=$(jq '. | length' "$output_file")
            total_chapters=$((total_chapters + chapter_count))
            skipped_books=$((skipped_books + 1))
            return 0
        fi
    fi

    while [[ $retry -lt $max_retries ]]; do
        if curl --fail -s -S -o "$output_file" "$url" 2>/dev/null; then
            # Validate and count chapters
            if jq -e '. | length' "$output_file" > /dev/null 2>&1; then
                local chapter_count=$(jq '. | length' "$output_file")
                successful_books=$((successful_books + 1))
                total_chapters=$((total_chapters + chapter_count))
                log_success "✓ Book $book_id ($book_name): $chapter_count chapters"
                return 0
            else
                log_warning "  Invalid JSON for book $book_id"
                rm -f "$output_file"
            fi
        fi

        retry=$((retry + 1))
        if [[ $retry -lt $max_retries ]]; then
            log_info "  Retry $retry/$max_retries for book $book_id..."
            sleep $((retry * 3))  # Longer backoff for chapter lists
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
    # Find all book metadata files
    shopt -s nullglob
    local book_files=("$DATA_DIR"/book_*.json)

    if [[ ${#book_files[@]} -eq 0 ]]; then
        log_warning "No book metadata files found in $DATA_DIR"
        log_info "Run sync_books.sh first to fetch book metadata"
        exit 1
    fi

    # Filter out chapter files
    book_files=($(printf '%s\n' "${book_files[@]}" | grep -v '_chapters\.json$'))

    total_books=${#book_files[@]}

    log_info "Starting chapter list sync"
    log_info "Total books:          $total_books"
    log_info "Rate limit:           ${SLEEP_BETWEEN_CALLS}s between requests"
    echo ""

    local start_time=$(date +%s)
    local current_book=0

    for book_file in "${book_files[@]}"; do
        current_book=$((current_book + 1))

        # Progress indicator
        if [[ $((current_book % 10)) -eq 0 ]]; then
            local progress=$((current_book * 100 / total_books))
            log_info "Progress: ${current_book}/${total_books} (${progress}%) - ${total_chapters} chapters so far"
        fi

        fetch_chapter_list "$book_file"

        # Rate limiting
        if [[ $current_book -lt $total_books ]]; then
            sleep "$SLEEP_BETWEEN_CALLS"
        fi
    done

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    # Summary
    echo ""
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "Chapter List Sync Complete"
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Total books:          $total_books"
    log_info "Newly synced:         $successful_books"
    log_info "Skipped (cached):     $skipped_books"
    log_info "Failed:               $failed_books"
    log_info "Total chapters:       $total_chapters"
    log_info "Duration:             ${minutes}m ${seconds}s"
    log_info "Data saved to:        $DATA_DIR"
    echo ""

    # Save chapter inventory
    local inventory_file="${DATA_DIR}/chapter_inventory.txt"
    {
        echo "# Chapter Inventory - Generated $(date '+%Y-%m-%d %H:%M:%S')"
        echo "# Book_ID | Book_Name | Chapter_Count"
        for book_file in "${book_files[@]}"; do
            local book_id=$(jq -r '.book_id' "$book_file" 2>/dev/null)
            local book_name=$(jq -r '.book_name // "Unknown"' "$book_file" 2>/dev/null)
            local chapters_file="${DATA_DIR}/book_${book_id}_chapters.json"
            if [[ -f "$chapters_file" ]]; then
                local chapter_count=$(jq '. | length' "$chapters_file" 2>/dev/null || echo 0)
                echo "$book_id | $book_name | $chapter_count"
            fi
        done
    } > "$inventory_file"

    log_info "Chapter inventory saved to: $inventory_file"
    echo ""
}

main "$@"
