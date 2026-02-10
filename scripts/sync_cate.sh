#!/bin/bash
max_cat=7
max_pag=5
#for c in {1..$max_cat}
for (( c=1; c<=max_cat; c++ ))
do
  echo $c
  for (( p=1; p<=max_pag; p++ ))
  do
    echo fetch category $c and page $p
    curl "localhost:8000/xsw/api/categories/$c/books?page=$p" > dist/c${c}_p${p}.json
  done
done

#for j in dist/c*json
#do
#  echo fetch book $j
#  curl "localhost:8000/xsw/api/books/$j" > dist/i$j.json
#  curl "http://localhost:8000/xsw/api/books/$j/chapters?page=1&nocache=true&www=false&all=true" > dist/b$j.json
#done

#for b in dist/i*json
#do
#  echo fetch book content $b
#  mx=$(jq .last_chapter_number $b)
#  i=$(jq .book_id $b)
#  for (( c=1; c<=mx; c++ ))
#  do
#    curl "localhost:8000/xsw/api/books/$i/chapters/${c}?nocache=true"
#    sleep 2
#  done
#done
