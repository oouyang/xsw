#!/usr/bin/env bash
#
# sync_unfinished.sh - Sync unfinished books in DB
#
# Queries the SQLite database to find books with:
#   1. Missing chapter lists (book exists but no chapters in DB)
#   2. Incomplete content (chapters exist but text is NULL)
# Then calls the API to fill the gaps.
#
# This script works with data already in the DB — it does NOT discover
# new books. Use sync_categories.sh + sync_books.sh for discovery.
#
# Usage:
#   ./sync_unfinished.sh                    # Sync all unfinished books
#   ./sync_unfinished.sh --chapters-only    # Only fetch missing chapter lists
#   ./sync_unfinished.sh --content-only     # Only fetch missing chapter content
#   ./sync_unfinished.sh --book cr382b      # Sync a specific book only
#   ./sync_unfinished.sh --dry-run          # Show what would be synced
#   ./sync_unfinished.sh --limit 10         # Process at most 10 books
#
# Environment variables:
#   API_BASE              - API base URL (default: http://localhost:8000/xsw/api)
#   DB_PATH               - SQLite database path (default: /app/data/xsw_cache.db)
#   SLEEP_CHAPTERS        - Delay between chapter list requests (default: 3.0)
#   SLEEP_CONTENT         - Delay between content requests (default: 5.0)
#   MAX_CONSECUTIVE_FAILS - Stop after N consecutive failures (default: 10)
#

set -euo pipefail

# Configuration
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
DB_PATH="${DB_PATH:-/app/data/xsw_cache.db}"
SLEEP_CHAPTERS="${SLEEP_CHAPTERS:-3.0}"
SLEEP_CONTENT="${SLEEP_CONTENT:-5.0}"
MAX_CONSECUTIVE_FAILS="${MAX_CONSECUTIVE_FAILS:-10}"

# Options
MODE="all"          # all | chapters | content
DRY_RUN=false
SINGLE_BOOK=""
BOOK_LIMIT=0        # 0 = no limit

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --chapters-only)  MODE="chapters"; shift ;;
        --content-only)   MODE="content"; shift ;;
        --dry-run)        DRY_RUN=true; shift ;;
        --book)           SINGLE_BOOK="$2"; shift 2 ;;
        --limit)          BOOK_LIMIT="$2"; shift 2 ;;
        --db)             DB_PATH="$2"; shift 2 ;;
        -h|--help)
            head -n 28 "$0" | tail -n +3 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[SYNC]${NC} $*"; }
log_success() { echo -e "${GREEN}[SYNC]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[SYNC]${NC} $*"; }
log_error()   { echo -e "${RED}[SYNC]${NC} $*"; }

# Verify prerequisites
if ! command -v sqlite3 &>/dev/null; then
    log_error "sqlite3 is required but not installed"
    exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
    log_error "Database not found: $DB_PATH"
    log_info "Set DB_PATH to your database location"
    log_info "  Docker:  DB_PATH=/app/data/xsw_cache.db"
    log_info "  Local:   DB_PATH=./xsw_cache.db"
    exit 1
fi

# Check API availability
check_api() {
    if curl --fail -s "${API_BASE}/health" > /dev/null 2>&1; then
        log_success "API available at ${API_BASE}"
        return 0
    else
        log_error "API not available at ${API_BASE}"
        return 1
    fi
}

# ─── Database queries ─────────────────────────────────────────────

# Skip pure-digit book IDs — those are legacy m.xsw.tw data that no
# longer resolve on czbooks.net (which uses alphanumeric IDs like cr382b).
# GLOB pattern: match IDs containing at least one non-digit character.
SKIP_OLD="AND b.id GLOB '*[^0-9]*'"
SKIP_OLD_CH="AND c.book_id GLOB '*[^0-9]*'"

# Books with no chapters in DB at all
query_books_without_chapters() {
    local where_clause=""
    if [[ -n "$SINGLE_BOOK" ]]; then
        where_clause="AND b.id = '${SINGLE_BOOK}'"
    fi
    local limit_clause=""
    if [[ $BOOK_LIMIT -gt 0 ]]; then
        limit_clause="LIMIT ${BOOK_LIMIT}"
    fi

    sqlite3 "$DB_PATH" <<-SQL
        SELECT b.id, b.name, COALESCE(b.last_chapter_num, 0)
        FROM books b
        LEFT JOIN chapters c ON c.book_id = b.id
        WHERE c.id IS NULL ${SKIP_OLD} ${where_clause}
        ORDER BY b.last_scraped_at DESC
        ${limit_clause};
SQL
}

# Books where chapter count in DB < last_chapter_num (incomplete chapter list)
query_books_with_missing_chapters() {
    local where_clause=""
    if [[ -n "$SINGLE_BOOK" ]]; then
        where_clause="AND b.id = '${SINGLE_BOOK}'"
    fi
    local limit_clause=""
    if [[ $BOOK_LIMIT -gt 0 ]]; then
        limit_clause="LIMIT ${BOOK_LIMIT}"
    fi

    sqlite3 "$DB_PATH" <<-SQL
        SELECT b.id, b.name, COALESCE(b.last_chapter_num, 0), COUNT(c.id)
        FROM books b
        LEFT JOIN chapters c ON c.book_id = b.id
        WHERE b.last_chapter_num IS NOT NULL
          AND b.last_chapter_num > 0
          ${SKIP_OLD} ${where_clause}
        GROUP BY b.id
        HAVING COUNT(c.id) < b.last_chapter_num
        ORDER BY (b.last_chapter_num - COUNT(c.id)) DESC
        ${limit_clause};
SQL
}

# Chapters with no content (text is NULL), grouped by book
query_books_with_missing_content() {
    local where_clause=""
    if [[ -n "$SINGLE_BOOK" ]]; then
        where_clause="AND c.book_id = '${SINGLE_BOOK}'"
    fi
    local limit_clause=""
    if [[ $BOOK_LIMIT -gt 0 ]]; then
        limit_clause="LIMIT ${BOOK_LIMIT}"
    fi

    sqlite3 "$DB_PATH" <<-SQL
        SELECT c.book_id, COALESCE(b.name, '?'), COUNT(c.id),
               (SELECT COUNT(*) FROM chapters c2 WHERE c2.book_id = c.book_id)
        FROM chapters c
        LEFT JOIN books b ON b.id = c.book_id
        WHERE c.text IS NULL ${SKIP_OLD_CH} ${where_clause}
        GROUP BY c.book_id
        ORDER BY COUNT(c.id) DESC
        ${limit_clause};
SQL
}

# Get list of chapter numbers missing content for a specific book
query_missing_content_chapters() {
    local book_id=$1
    sqlite3 "$DB_PATH" <<-SQL
        SELECT chapter_num FROM chapters
        WHERE book_id = '${book_id}' AND text IS NULL
        ORDER BY chapter_num;
SQL
}

# ─── Sync functions ───────────────────────────────────────────────

consecutive_failures=0

# Fetch chapter list for a book via API (triggers web scrape + DB store)
sync_chapter_list() {
    local book_id=$1
    local book_name=$2
    local retry=0
    local max_retries=3
    local url="${API_BASE}/books/${book_id}/chapters?all=true"

    while [[ $retry -lt $max_retries ]]; do
        local http_code
        http_code=$(curl -w "%{http_code}" -s -o /dev/null "$url" 2>/dev/null)

        if [[ $http_code -eq 200 ]]; then
            consecutive_failures=0
            log_success "  ✓ Chapters synced: ${book_name} (${book_id})"
            return 0
        fi

        retry=$((retry + 1))
        if [[ $retry -lt $max_retries ]]; then
            log_warning "  Retry $retry/$max_retries (HTTP $http_code)"
            sleep $((retry * 2))
        fi
    done

    consecutive_failures=$((consecutive_failures + 1))
    log_error "  ✗ Failed: ${book_name} (${book_id}) HTTP $http_code"
    return 1
}

# Fetch single chapter content via API (triggers web scrape + DB store)
sync_chapter_content() {
    local book_id=$1
    local chapter_num=$2
    local retry=0
    local max_retries=3
    local url="${API_BASE}/books/${book_id}/chapters/${chapter_num}"

    while [[ $retry -lt $max_retries ]]; do
        local http_code
        http_code=$(curl -w "%{http_code}" -s -o /dev/null "$url" 2>/dev/null)

        if [[ $http_code -eq 200 ]]; then
            consecutive_failures=0
            return 0
        fi

        retry=$((retry + 1))
        if [[ $retry -lt $max_retries ]]; then
            sleep $((retry * 2))
        fi
    done

    consecutive_failures=$((consecutive_failures + 1))
    return 1
}

check_abort() {
    if [[ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILS ]]; then
        log_error ""
        log_error "Maximum consecutive failures reached: $consecutive_failures"
        log_error "The site may be blocking requests. Try again later."
        exit 1
    fi
}

# ─── Phase 1: Sync chapter lists ─────────────────────────────────

phase_sync_chapters() {
    log_info "═══════════════════════════════════════════════════"
    log_info "Phase 1: Sync missing chapter lists"
    log_info "═══════════════════════════════════════════════════"
    echo ""

    # Find books with zero chapters
    local no_chapters
    no_chapters=$(query_books_without_chapters)

    # Find books with fewer chapters than expected
    local missing_chapters
    missing_chapters=$(query_books_with_missing_chapters)

    # Combine and deduplicate book IDs
    local book_ids=()
    local book_names=()

    while IFS='|' read -r bid bname _; do
        [[ -z "$bid" ]] && continue
        book_ids+=("$bid")
        book_names+=("$bname")
    done <<< "$no_chapters"

    while IFS='|' read -r bid bname expected actual; do
        [[ -z "$bid" ]] && continue
        # Skip if already in list
        local found=false
        for existing in "${book_ids[@]+"${book_ids[@]}"}"; do
            if [[ "$existing" == "$bid" ]]; then
                found=true
                break
            fi
        done
        if [[ "$found" == false ]]; then
            book_ids+=("$bid")
            book_names+=("${bname} (have ${actual}/${expected})")
        fi
    done <<< "$missing_chapters"

    local total=${#book_ids[@]}
    if [[ $total -eq 0 ]]; then
        log_success "All books have complete chapter lists"
        echo ""
        return
    fi

    log_info "Found $total books needing chapter list sync"
    echo ""

    if [[ "$DRY_RUN" == true ]]; then
        for ((i=0; i<total; i++)); do
            log_info "  Would sync: ${book_ids[$i]} - ${book_names[$i]}"
        done
        echo ""
        return
    fi

    local synced=0
    local failed=0

    for ((i=0; i<total; i++)); do
        local bid="${book_ids[$i]}"
        local bname="${book_names[$i]}"

        log_info "[$((i+1))/$total] $bname"

        if sync_chapter_list "$bid" "$bname"; then
            synced=$((synced + 1))
        else
            failed=$((failed + 1))
            check_abort
        fi

        # Rate limit (skip for last)
        if [[ $((i+1)) -lt $total ]]; then
            sleep "$SLEEP_CHAPTERS"
        fi
    done

    echo ""
    log_success "Chapter lists: $synced synced, $failed failed out of $total"
    echo ""
}

# ─── Phase 2: Sync missing content ───────────────────────────────

phase_sync_content() {
    log_info "═══════════════════════════════════════════════════"
    log_info "Phase 2: Sync missing chapter content"
    log_info "═══════════════════════════════════════════════════"
    echo ""

    local books_data
    books_data=$(query_books_with_missing_content)

    if [[ -z "$books_data" ]]; then
        log_success "All chapters have content"
        echo ""
        return
    fi

    # Count totals
    local total_books=0
    local total_missing=0
    while IFS='|' read -r bid bname missing total_ch; do
        [[ -z "$bid" ]] && continue
        total_books=$((total_books + 1))
        total_missing=$((total_missing + missing))
    done <<< "$books_data"

    log_info "Found $total_missing chapters without content across $total_books books"
    echo ""

    if [[ "$DRY_RUN" == true ]]; then
        while IFS='|' read -r bid bname missing total_ch; do
            [[ -z "$bid" ]] && continue
            log_info "  Would sync: ${bid} - ${bname} (${missing}/${total_ch} missing)"
        done <<< "$books_data"
        echo ""
        return
    fi

    local synced_total=0
    local failed_total=0
    local book_index=0
    local start_time
    start_time=$(date +%s)

    while IFS='|' read -r bid bname missing total_ch; do
        [[ -z "$bid" ]] && continue
        book_index=$((book_index + 1))

        log_info "─── [$book_index/$total_books] $bname ($bid): $missing chapters to fetch ───"

        # Get the specific chapter numbers that need content
        local chapter_nums
        chapter_nums=$(query_missing_content_chapters "$bid")

        local ch_synced=0
        local ch_failed=0
        local ch_index=0
        local ch_total
        ch_total=$(echo "$chapter_nums" | wc -l)

        while IFS= read -r ch_num; do
            [[ -z "$ch_num" ]] && continue
            ch_index=$((ch_index + 1))

            if sync_chapter_content "$bid" "$ch_num"; then
                ch_synced=$((ch_synced + 1))
                synced_total=$((synced_total + 1))

                # Progress every 20 chapters
                if [[ $((ch_synced % 20)) -eq 0 ]]; then
                    log_info "  Progress: $ch_synced/$ch_total chapters"
                fi
            else
                ch_failed=$((ch_failed + 1))
                failed_total=$((failed_total + 1))
                log_warning "  ✗ Chapter $ch_num failed"
                check_abort
            fi

            # Rate limit (skip for last)
            if [[ $ch_index -lt $ch_total ]]; then
                sleep "$SLEEP_CONTENT"
            fi

        done <<< "$chapter_nums"

        log_success "  Done: $ch_synced synced, $ch_failed failed"
        echo ""

    done <<< "$books_data"

    local elapsed=$(( $(date +%s) - start_time ))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))

    echo ""
    log_success "Content sync: $synced_total synced, $failed_total failed"
    log_info "Duration: ${minutes}m ${seconds}s"
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────

main() {
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Sync Unfinished Books"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Database:     $DB_PATH"
    log_info "API:          $API_BASE"
    log_info "Mode:         $MODE"
    if [[ -n "$SINGLE_BOOK" ]]; then
        log_info "Book filter:  $SINGLE_BOOK"
    fi
    if [[ $BOOK_LIMIT -gt 0 ]]; then
        log_info "Book limit:   $BOOK_LIMIT"
    fi
    if [[ "$DRY_RUN" == true ]]; then
        log_warning "DRY RUN — no actual requests will be made"
    fi
    echo ""

    # Quick DB summary
    local db_books db_chapters db_with_content
    db_books=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM books;")
    db_chapters=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM chapters;")
    db_with_content=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM chapters WHERE text IS NOT NULL;")
    log_info "DB status: $db_books books, $db_chapters chapters ($db_with_content with content)"
    echo ""

    if [[ "$DRY_RUN" == false ]]; then
        check_api || exit 1
        echo ""
    fi

    local start_time
    start_time=$(date +%s)

    if [[ "$MODE" == "all" || "$MODE" == "chapters" ]]; then
        phase_sync_chapters
    fi

    if [[ "$MODE" == "all" || "$MODE" == "content" ]]; then
        phase_sync_content
    fi

    local elapsed=$(( $(date +%s) - start_time ))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))

    # Final DB summary
    db_chapters=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM chapters;")
    db_with_content=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM chapters WHERE text IS NOT NULL;")

    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_success "Sync Complete (${minutes}m ${seconds}s)"
    log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "DB now: $db_books books, $db_chapters chapters ($db_with_content with content)"
    echo ""
}

trap 'log_warning "Interrupted!"; exit 130' INT TERM

main "$@"
