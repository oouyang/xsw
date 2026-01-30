#!/usr/bin/env bash
#
# sync_content_enhanced.sh - Sync chapter content with intelligent rate limiting
#
# This is the most intensive phase - fetches actual chapter content
# Implements multiple safety features to avoid getting blocked:
#   - Configurable delays between requests
#   - Exponential backoff on failures
#   - Progress checkpoints
#   - Resume capability
#   - Adaptive rate limiting based on response times
#
# Environment variables:
#   SLEEP_BETWEEN_CALLS   - Base delay between requests (default: 5.0)
#   API_BASE              - API base URL (default: http://localhost:8000/xsw/api)
#   DATA_DIR              - Data storage directory (default: ./sync_data)
#   MAX_FAILURES          - Max consecutive failures before stopping (default: 10)
#   CHECKPOINT_INTERVAL   - Save progress every N chapters (default: 100)
#   ADAPTIVE_RATE_LIMIT   - Enable adaptive rate limiting (default: true)
#

set -euo pipefail

# Configuration
SLEEP_BETWEEN_CALLS="${SLEEP_BETWEEN_CALLS:-5.0}"
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
DATA_DIR="${DATA_DIR:-./sync_data}"
MAX_FAILURES="${MAX_FAILURES:-10}"
CHECKPOINT_INTERVAL="${CHECKPOINT_INTERVAL:-100}"
ADAPTIVE_RATE_LIMIT="${ADAPTIVE_RATE_LIMIT:-true}"

# State files
CHECKPOINT_FILE="${DATA_DIR}/content_sync_checkpoint.txt"
PROGRESS_FILE="${DATA_DIR}/content_sync_progress.txt"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[CONTENT]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[CONTENT]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[CONTENT]${NC} $*"
}

log_error() {
    echo -e "${RED}[CONTENT]${NC} $*"
}

# Track statistics
total_chapters=0
synced_chapters=0
skipped_chapters=0
failed_chapters=0
consecutive_failures=0
current_delay=$SLEEP_BETWEEN_CALLS

# Adaptive rate limiting
update_delay() {
    local response_time=$1

    if [[ "$ADAPTIVE_RATE_LIMIT" != "true" ]]; then
        return
    fi

    # If response is slow (> 3s), increase delay
    if (( $(echo "$response_time > 3.0" | bc -l) )); then
        current_delay=$(echo "$current_delay * 1.2" | bc)
        log_warning "  Slow response detected (${response_time}s), increasing delay to ${current_delay}s"
    # If response is fast (< 0.5s), decrease delay slightly
    elif (( $(echo "$response_time < 0.5" | bc -l) )) && (( $(echo "$current_delay > 1.0" | bc -l) )); then
        current_delay=$(echo "$current_delay * 0.95" | bc)
    fi

    # Cap delay between 1s and 30s
    if (( $(echo "$current_delay < 1.0" | bc -l) )); then
        current_delay=1.0
    elif (( $(echo "$current_delay > 30.0" | bc -l) )); then
        current_delay=30.0
        log_warning "  Maximum delay reached (30s), site may be rate limiting"
    fi
}

# Load checkpoint
load_checkpoint() {
    if [[ -f "$CHECKPOINT_FILE" ]]; then
        cat "$CHECKPOINT_FILE"
    else
        echo ""
    fi
}

# Save checkpoint
save_checkpoint() {
    local book_id=$1
    local chapter_num=$2
    echo "${book_id}:${chapter_num}" > "$CHECKPOINT_FILE"
}

# Save progress stats
save_progress() {
    {
        echo "timestamp=$(date '+%Y-%m-%d %H:%M:%S')"
        echo "total_chapters=$total_chapters"
        echo "synced_chapters=$synced_chapters"
        echo "skipped_chapters=$skipped_chapters"
        echo "failed_chapters=$failed_chapters"
        echo "current_delay=$current_delay"
    } > "$PROGRESS_FILE"
}

# Fetch chapter content
fetch_chapter_content() {
    local book_id=$1
    local chapter_num=$2
    local book_name=$3
    local output_file="${DATA_DIR}/content_${book_id}_${chapter_num}.json"
    local url="${API_BASE}/books/${book_id}/chapters/${chapter_num}"
    local retry=0
    local max_retries=3

    # Skip if already exists and is valid
    if [[ -f "$output_file" ]]; then
        if jq -e '.text' "$output_file" > /dev/null 2>&1; then
            local text_length=$(jq -r '.text | length' "$output_file" 2>/dev/null || echo 0)
            if [[ $text_length -gt 50 ]]; then  # Reasonable chapter length
                skipped_chapters=$((skipped_chapters + 1))
                return 0
            fi
        fi
        # Invalid or incomplete, remove and re-fetch
        rm -f "$output_file"
    fi

    while [[ $retry -lt $max_retries ]]; do
        local start_time=$(date +%s.%N)

        if curl --fail -s -S -o "$output_file" "$url" 2>/dev/null; then
            local end_time=$(date +%s.%N)
            local response_time=$(echo "$end_time - $start_time" | bc)

            # Validate chapter content
            if jq -e '.text' "$output_file" > /dev/null 2>&1; then
                local text_length=$(jq -r '.text | length' "$output_file" 2>/dev/null || echo 0)
                local title=$(jq -r '.title // "Chapter '$chapter_num'"' "$output_file" 2>/dev/null)

                if [[ $text_length -gt 50 ]]; then
                    synced_chapters=$((synced_chapters + 1))
                    consecutive_failures=0  # Reset failure counter
                    log_success "✓ Book $book_id Ch.$chapter_num: $title (${text_length} chars, ${response_time}s)"

                    # Update adaptive delay
                    update_delay "$response_time"

                    return 0
                else
                    log_warning "  Chapter $chapter_num too short (${text_length} chars), might be invalid"
                    rm -f "$output_file"
                fi
            else
                log_warning "  Invalid JSON for chapter $chapter_num"
                rm -f "$output_file"
            fi
        fi

        # Failed attempt
        retry=$((retry + 1))
        consecutive_failures=$((consecutive_failures + 1))

        if [[ $retry -lt $max_retries ]]; then
            local backoff=$((retry * retry * 2))  # Exponential backoff: 2s, 8s, 18s
            log_warning "  Retry $retry/$max_retries for book $book_id ch.$chapter_num (waiting ${backoff}s)..."
            sleep $backoff
        else
            failed_chapters=$((failed_chapters + 1))
            log_error "  ✗ Failed after $max_retries retries: book $book_id chapter $chapter_num"
            rm -f "$output_file"

            # Check if we're hitting too many failures
            if [[ $consecutive_failures -ge $MAX_FAILURES ]]; then
                log_error "  Maximum consecutive failures reached ($MAX_FAILURES)"
                log_error "  The site may be blocking requests. Consider:"
                log_error "    1. Increasing SLEEP_BETWEEN_CALLS (currently: ${current_delay}s)"
                log_error "    2. Using --ultra-slow profile"
                log_error "    3. Trying again later"
                log_error "  Progress saved. Use --resume to continue from checkpoint."
                return 2
            fi

            return 1
        fi
    done
}

# Main sync loop
main() {
    log_info "Starting chapter content sync (INTENSIVE PHASE)"
    log_info "Base rate limit:      ${SLEEP_BETWEEN_CALLS}s between requests"
    log_info "Adaptive rate limit:  $ADAPTIVE_RATE_LIMIT"
    log_info "Max failures:         $MAX_FAILURES consecutive"
    log_info "Checkpoint interval:  Every $CHECKPOINT_INTERVAL chapters"
    echo ""

    # Find all chapter list files
    shopt -s nullglob
    local chapter_files=("$DATA_DIR"/book_*_chapters.json)

    if [[ ${#chapter_files[@]} -eq 0 ]]; then
        log_warning "No chapter list files found in $DATA_DIR"
        log_info "Run sync_chapters_enhanced.sh first"
        exit 1
    fi

    # Count total chapters
    for chapter_file in "${chapter_files[@]}"; do
        local count=$(jq '. | length' "$chapter_file" 2>/dev/null || echo 0)
        total_chapters=$((total_chapters + count))
    done

    log_info "Total books:          ${#chapter_files[@]}"
    log_info "Total chapters:       $total_chapters"

    # Load checkpoint if exists
    local checkpoint=$(load_checkpoint)
    local resume_book=""
    local resume_chapter=0

    if [[ -n "$checkpoint" ]]; then
        IFS=':' read -r resume_book resume_chapter <<< "$checkpoint"
        log_info "Resuming from:        Book $resume_book, Chapter $resume_chapter"
    fi

    echo ""

    local start_time=$(date +%s)
    local processed_chapters=0
    local should_skip=false

    # If resuming, skip until we reach checkpoint
    if [[ -n "$resume_book" ]]; then
        should_skip=true
    fi

    # Process each book
    for chapter_file in "${chapter_files[@]}"; do
        # Extract book_id from filename (book_123_chapters.json -> 123)
        local book_id=$(basename "$chapter_file" | sed 's/book_\([0-9]*\)_chapters\.json/\1/')

        # Get book name
        local book_metadata_file="${DATA_DIR}/book_${book_id}.json"
        local book_name="Unknown"
        if [[ -f "$book_metadata_file" ]]; then
            book_name=$(jq -r '.book_name // "Unknown"' "$book_metadata_file" 2>/dev/null)
        fi

        # Get chapter list
        local chapters=$(jq -r '.[].number' "$chapter_file" 2>/dev/null)

        log_info "═══════════════════════════════════════════════════"
        log_info "Book: $book_name (ID: $book_id)"
        log_info "═══════════════════════════════════════════════════"

        # Process each chapter
        while IFS= read -r chapter_num; do
            # Skip if we haven't reached resume point
            if [[ "$should_skip" == true ]]; then
                if [[ "$book_id" == "$resume_book" ]] && [[ "$chapter_num" -ge "$resume_chapter" ]]; then
                    should_skip=false
                    log_info "Resuming from this chapter..."
                else
                    continue
                fi
            fi

            processed_chapters=$((processed_chapters + 1))

            # Progress indicator
            if [[ $((processed_chapters % 50)) -eq 0 ]]; then
                local progress=$((processed_chapters * 100 / total_chapters))
                local elapsed=$(($(date +%s) - start_time))
                local rate=$(echo "scale=2; $processed_chapters / $elapsed * 60" | bc)
                log_info "Progress: ${processed_chapters}/${total_chapters} (${progress}%) - ${rate} chapters/min"
                log_info "Stats: ✓$synced_chapters ⊘$skipped_chapters ✗$failed_chapters - Delay: ${current_delay}s"
            fi

            # Fetch chapter content
            if ! fetch_chapter_content "$book_id" "$chapter_num" "$book_name"; then
                local fetch_result=$?
                if [[ $fetch_result -eq 2 ]]; then
                    # Critical failure, stop syncing
                    save_checkpoint "$book_id" "$chapter_num"
                    save_progress
                    exit 1
                fi
            fi

            # Save checkpoint periodically
            if [[ $((processed_chapters % CHECKPOINT_INTERVAL)) -eq 0 ]]; then
                save_checkpoint "$book_id" "$chapter_num"
                save_progress
                log_info "Checkpoint saved: Book $book_id, Chapter $chapter_num"
            fi

            # Rate limiting
            sleep "$current_delay"

        done <<< "$chapters"

        echo ""  # Blank line between books
    done

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))

    # Final summary
    echo ""
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "Chapter Content Sync Complete"
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Total chapters:       $total_chapters"
    log_info "Newly synced:         $synced_chapters"
    log_info "Skipped (cached):     $skipped_chapters"
    log_info "Failed:               $failed_chapters"
    log_info "Duration:             ${hours}h ${minutes}m ${seconds}s"
    log_info "Average delay:        ${current_delay}s"
    log_info "Data saved to:        $DATA_DIR"
    echo ""

    # Clear checkpoint on successful completion
    rm -f "$CHECKPOINT_FILE"
    save_progress
}

# Trap to save progress on interrupt
trap 'log_warning "Sync interrupted! Progress saved. Use --resume to continue."; save_progress; exit 130' INT TERM

main "$@"
