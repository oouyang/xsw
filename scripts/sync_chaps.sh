#!/usr/bin/env bash
#
# sync_chaps.sh - Quick chapter list fetch for all discovered books
#
# Reads book IDs from category JSON files and fetches chapter lists + metadata.
# Book IDs are alphanumeric (e.g. "cr382b") on czbooks.net.
#

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/xsw/api}"
OUT_DIR="${OUT_DIR:-dist}"

for b in $(jq -r '.[].book_id' "${OUT_DIR}"/c_*_p*.json 2>/dev/null | sort -u); do
    echo "fetch book $b"
    curl -s "${API_BASE}/books/${b}" > "${OUT_DIR}/i${b}.json"
    curl -s "${API_BASE}/books/${b}/chapters?page=1&nocache=true&www=false&all=true" > "${OUT_DIR}/b${b}.json"
done
