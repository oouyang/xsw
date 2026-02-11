#!/bin/bash
#
# sync_cate.sh - Quick category book discovery (simple version)
#
# Discovers category slugs from /categories API, then fetches book lists.
# czbooks.net uses slug-based categories (e.g. "xuanhuan", "dushi").
#
# Usage:
#   ./sync_cate.sh              # Sync all categories, 5 pages each
#   MAX_PAGES=10 ./sync_cate.sh # Sync with 10 pages per category
#

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
MAX_PAGES="${MAX_PAGES:-5}"
OUT_DIR="${OUT_DIR:-dist}"

mkdir -p "$OUT_DIR"

# Step 1: Discover category slugs from API
echo "Discovering categories..."
categories_json=$(curl -s "${API_BASE}/categories")
slugs=$(echo "$categories_json" | jq -r '.[].id')

if [[ -z "$slugs" ]]; then
    echo "Error: No categories found" >&2
    exit 1
fi

echo "$categories_json" | jq -r '.[] | "  \(.id): \(.name)"'
echo ""

# Step 2: Fetch book lists for each category
for slug in $slugs; do
    echo "Category: $slug"
    for (( p=1; p<=MAX_PAGES; p++ )); do
        echo "  fetch category $slug page $p"
        curl -s "${API_BASE}/categories/${slug}/books?page=${p}" > "${OUT_DIR}/c_${slug}_p${p}.json"
    done
done
