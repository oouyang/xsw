#!/usr/bin/env bash
for b in $(jq -r .[].book_id dist/c*json);
do
  echo fetch book $b
  curl "localhost:8000/xsw/api/books/$j" > dist/i$b.json
  curl "http://localhost:8000/xsw/api/books/${b}/chapters?page=1&nocache=true&www=false&all=true" > dist/b$b.json

done
