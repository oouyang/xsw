#!/usr/bin/env bash
#
# sync_full.sh - Master script to sync entire site with intelligent rate limiting
#
# This script orchestrates a full site sync in phases to avoid overwhelming
# the source site and getting blocked by rate limiting.
#
# Usage:
#   ./sync_full.sh [OPTIONS]
#
# Options:
#   --fast          Use faster sync (higher risk of blocking)
#   --slow          Use slower sync (safer, default)
#   --ultra-slow    Use ultra-slow sync (maximum safety)
#   --categories N  Limit to first N categories (default: all discovered)
#   --pages N       Pages per category (default: 10)
#   --resume        Resume from last checkpoint
#   --dry-run       Show what would be synced without syncing
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration directory
SYNC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SYNC_DIR}/sync_data"
LOG_DIR="${DATA_DIR}/logs"
CHECKPOINT_FILE="${DATA_DIR}/checkpoint.txt"

# API configuration
API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"

# Default rate limiting profiles
declare -A RATE_PROFILES=(
    ["fast"]="0.5:1.0:2.0"        # category:book:chapter delays
    ["slow"]="2.0:3.0:5.0"        # default
    ["ultra-slow"]="5.0:10.0:15.0"
)

# Default configuration
PROFILE="slow"
MAX_CATEGORIES=0
PAGES_PER_CATEGORY=10
RESUME_MODE=false
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fast)
            PROFILE="fast"
            shift
            ;;
        --slow)
            PROFILE="slow"
            shift
            ;;
        --ultra-slow)
            PROFILE="ultra-slow"
            shift
            ;;
        --categories)
            MAX_CATEGORIES="$2"
            shift 2
            ;;
        --pages)
            PAGES_PER_CATEGORY="$2"
            shift 2
            ;;
        --resume)
            RESUME_MODE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            head -n 20 "$0" | tail -n +3 | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Parse rate profile
IFS=':' read -r CATEGORY_DELAY BOOK_DELAY CHAPTER_DELAY <<< "${RATE_PROFILES[$PROFILE]}"

# Create directories
mkdir -p "$DATA_DIR" "$LOG_DIR"

# Logging functions
log() {
    local level=$1
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] $*" | tee -a "${LOG_DIR}/sync_$(date +%Y%m%d).log"
}

log_info() {
    echo -e "${BLUE}ℹ${NC} $*"
    log "INFO" "$*"
}

log_success() {
    echo -e "${GREEN}✓${NC} $*"
    log "SUCCESS" "$*"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $*"
    log "WARNING" "$*"
}

log_error() {
    echo -e "${RED}✗${NC} $*"
    log "ERROR" "$*"
}

# Checkpoint management
save_checkpoint() {
    local phase=$1
    local progress=$2
    echo "${phase}:${progress}" > "$CHECKPOINT_FILE"
}

load_checkpoint() {
    if [[ -f "$CHECKPOINT_FILE" ]] && [[ "$RESUME_MODE" == true ]]; then
        cat "$CHECKPOINT_FILE"
    else
        echo "START:0"
    fi
}

# Check if API is available
check_api() {
    log_info "Checking API availability..."
    if curl --fail -s "${API_BASE}/health" > /dev/null 2>&1; then
        log_success "API is available at ${API_BASE}"
        return 0
    else
        log_error "API is not available at ${API_BASE}"
        log_error "Please ensure the backend is running: uvicorn main_optimized:app --port 8000"
        return 1
    fi
}

# Display sync plan
display_plan() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              FULL SITE SYNC PLAN                               ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Profile:              ${PROFILE}"
    if [[ $MAX_CATEGORIES -eq 0 ]]; then
        echo "Categories to sync:   all (discovered from API)"
    else
        echo "Categories to sync:   ${MAX_CATEGORIES}"
    fi
    echo "Pages per category:   ${PAGES_PER_CATEGORY}"
    echo "API Base URL:         ${API_BASE}"
    echo ""
    echo "Rate Limiting:"
    echo "  - Category delay:   ${CATEGORY_DELAY}s"
    echo "  - Book delay:       ${BOOK_DELAY}s"
    echo "  - Chapter delay:    ${CHAPTER_DELAY}s"
    echo ""
    echo "Estimated sync phases:"
    echo "  1. Categories       (discover + ${PAGES_PER_CATEGORY} pages each)"
    echo "  2. Book metadata    (variable, based on discovery)"
    echo "  3. Chapter lists    (variable, based on books found)"
    echo "  4. Chapter content  (high volume, throttled)"
    echo ""

    if [[ "$DRY_RUN" == true ]]; then
        echo "DRY RUN MODE: No actual syncing will occur"
        echo ""
    fi

    if [[ "$RESUME_MODE" == true ]]; then
        local checkpoint=$(load_checkpoint)
        echo "RESUME MODE: Will continue from checkpoint: ${checkpoint}"
        echo ""
    fi
}

# Phase 1: Sync categories and discover books
phase1_sync_categories() {
    log_info "PHASE 1: Syncing categories and discovering books"

    if [[ "$DRY_RUN" == true ]]; then
        log_info "Would sync ${MAX_CATEGORIES} categories with ${PAGES_PER_CATEGORY} pages each"
        return 0
    fi

    export SLEEP_BETWEEN_CALLS="$CATEGORY_DELAY"
    export MAX_CATEGORIES
    export PAGES_PER_CATEGORY
    export API_BASE
    export DATA_DIR

    bash "${SYNC_DIR}/sync_categories.sh"

    save_checkpoint "PHASE1" "COMPLETE"
    log_success "Phase 1 complete: Categories synced"
}

# Phase 2: Sync book metadata
phase2_sync_books() {
    log_info "PHASE 2: Syncing book metadata"

    if [[ "$DRY_RUN" == true ]]; then
        local book_count=$(find "$DATA_DIR" -name "c_*_p*.json" -exec jq -r '.[].book_id' {} \; 2>/dev/null | sort -u | wc -l)
        log_info "Would sync metadata for ~${book_count} books"
        return 0
    fi

    export SLEEP_BETWEEN_CALLS="$BOOK_DELAY"
    export API_BASE
    export DATA_DIR

    bash "${SYNC_DIR}/sync_books.sh"

    save_checkpoint "PHASE2" "COMPLETE"
    log_success "Phase 2 complete: Book metadata synced"
}

# Phase 3: Sync chapter lists
phase3_sync_chapters() {
    log_info "PHASE 3: Syncing chapter lists"

    if [[ "$DRY_RUN" == true ]]; then
        local book_count=$(find "$DATA_DIR" -name "book_*.json" -type f 2>/dev/null | wc -l)
        log_info "Would sync chapter lists for ${book_count} books"
        return 0
    fi

    export SLEEP_BETWEEN_CALLS="$BOOK_DELAY"
    export API_BASE
    export DATA_DIR

    bash "${SYNC_DIR}/sync_chapters_enhanced.sh"

    save_checkpoint "PHASE3" "COMPLETE"
    log_success "Phase 3 complete: Chapter lists synced"
}

# Phase 4: Sync chapter content (most intensive)
phase4_sync_content() {
    log_info "PHASE 4: Syncing chapter content (this will take a while...)"

    if [[ "$DRY_RUN" == true ]]; then
        local total_chapters=$(find "$DATA_DIR" -name "book_*_chapters.json" -exec jq '. | length' {} \; 2>/dev/null | awk '{sum+=$1} END {print sum}')
        local estimated_time=$((total_chapters * ${CHAPTER_DELAY%.*} / 60))
        log_info "Would sync ~${total_chapters} chapters"
        log_info "Estimated time: ~${estimated_time} minutes"
        return 0
    fi

    export SLEEP_BETWEEN_CALLS="$CHAPTER_DELAY"
    export API_BASE
    export DATA_DIR

    bash "${SYNC_DIR}/sync_content_enhanced.sh"

    save_checkpoint "PHASE4" "COMPLETE"
    log_success "Phase 4 complete: Chapter content synced"
}

# Generate sync report
generate_report() {
    local report_file="${LOG_DIR}/sync_report_$(date +%Y%m%d_%H%M%S).txt"

    log_info "Generating sync report..."

    {
        echo "╔════════════════════════════════════════════════════════════════╗"
        echo "║                   SYNC COMPLETION REPORT                       ║"
        echo "╚════════════════════════════════════════════════════════════════╝"
        echo ""
        echo "Sync completed at: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "Profile used: ${PROFILE}"
        echo ""
        echo "Statistics:"

        # Count categories
        local cat_count=$(find "$DATA_DIR" -name "c_*_p*.json" -type f 2>/dev/null | wc -l)
        echo "  Categories synced:    ${cat_count}"

        # Count unique books
        local book_count=$(find "$DATA_DIR" -name "book_*.json" -type f 2>/dev/null | wc -l)
        echo "  Books discovered:     ${book_count}"

        # Count chapter lists
        local chap_list_count=$(find "$DATA_DIR" -name "book_*_chapters.json" -type f 2>/dev/null | wc -l)
        echo "  Chapter lists synced: ${chap_list_count}"

        # Count total chapters
        local total_chapters=$(find "$DATA_DIR" -name "book_*_chapters.json" -exec jq '. | length' {} \; 2>/dev/null | awk '{sum+=$1} END {print sum}')
        echo "  Total chapters:       ${total_chapters}"

        # Count synced content
        local synced_content=$(find "$DATA_DIR" -name "content_*.json" -type f 2>/dev/null | wc -l)
        echo "  Content synced:       ${synced_content}"

        # Database size
        if [[ -f "${SYNC_DIR}/xsw_cache.db" ]]; then
            local db_size=$(du -h "${SYNC_DIR}/xsw_cache.db" | cut -f1)
            echo "  Database size:        ${db_size}"
        fi

        echo ""
        echo "Data location:         ${DATA_DIR}"
        echo "Log location:          ${LOG_DIR}"

    } | tee "$report_file"

    log_success "Report saved to: ${report_file}"
}

# Main execution
main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              看小說 (XSW) - FULL SITE SYNC                     ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # Check prerequisites
    if ! command -v jq &> /dev/null; then
        log_error "jq is required but not installed. Please install: apt-get install jq"
        exit 1
    fi

    # Check API availability
    if ! check_api; then
        exit 1
    fi

    # Display plan
    display_plan

    # Confirm unless dry-run
    if [[ "$DRY_RUN" == false ]]; then
        echo -n "Proceed with sync? [y/N] "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Sync cancelled by user"
            exit 0
        fi
        echo ""
    fi

    # Load checkpoint if resuming
    local checkpoint=$(load_checkpoint)
    local resume_phase="${checkpoint%%:*}"

    # Execute phases
    local start_time=$(date +%s)

    if [[ "$resume_phase" != "PHASE1" ]] || [[ "$resume_phase" == "START" ]]; then
        phase1_sync_categories
    fi

    if [[ "$resume_phase" != "PHASE2" ]] || [[ "$resume_phase" == "START" ]]; then
        phase2_sync_books
    fi

    if [[ "$resume_phase" != "PHASE3" ]] || [[ "$resume_phase" == "START" ]]; then
        phase3_sync_chapters
    fi

    if [[ "$resume_phase" != "PHASE4" ]] || [[ "$resume_phase" == "START" ]]; then
        phase4_sync_content
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))

    echo ""
    log_success "✨ Full sync completed successfully!"
    log_info "Total time: ${hours}h ${minutes}m ${seconds}s"
    echo ""

    # Generate report
    if [[ "$DRY_RUN" == false ]]; then
        generate_report
    fi

    # Clear checkpoint
    rm -f "$CHECKPOINT_FILE"
}

# Trap errors and interrupts
trap 'log_error "Sync interrupted. Use --resume to continue from last checkpoint."; exit 1' INT TERM

# Run main
main "$@"
