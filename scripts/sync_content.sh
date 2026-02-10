#!/usr/bin/env bash
set -euo pipefail

# If no files match, the glob stays empty rather than literal
shopt -s nullglob

# Optional: slow down requests (seconds)
SLEEP_BETWEEN_CALLS="${SLEEP_BETWEEN_CALLS:-2}"

for b in dist/i*json; do
  echo "fetch book content: $b"

  # Extract as raw values (no quotes). jq -e fails if path is missing/null.
  if ! mx=$(jq -er '.last_chapter_number' "$b"); then
    echo "Error: last_chapter_number not found in $b" >&2
    continue
  fi
  if ! i=$(jq -er '.book_id' "$b"); then
    echo "Error: book_id not found in $b" >&2
    continue
  fi

  # Validate numeric fields
  if ! [[ "$mx" =~ ^[0-9]+$ ]] || ! [[ "$i" =~ ^[0-9]+$ ]]; then
    echo "Error: non-numeric mx ($mx) or book_id ($i) in $b" >&2
    continue
  fi

  # Skip empty/zero chapter counts
  if (( mx < 1 )); then
    echo "Info: no chapters to fetch for book_id=$i (mx=$mx)" >&2
    continue
  fi

  for (( c=1; c<=mx; c++ )); do
    url="http://localhost:8000/xsw/api/books/$i/chapters/${c}?nocache=true"
    echo "GET $url"
    # --fail: non-2xx makes curl exit non-zero; -S shows errors; -s quiets output except errors
    if ! curl --fail -S -s "$url"; then
      echo "Warning: request failed for book_id=$i chapter=$c" >&2
    fi
    sleep "$SLEEP_BETWEEN_CALLS"
  done
done
