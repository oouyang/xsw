# Comprehensive Search API

## Overview

The enhanced search API provides powerful full-text search capabilities across:
- **Book names** and **authors**
- **Chapter titles**
- **Chapter content** (full-text search)

Results are relevance-scored and grouped by book for easy browsing.

## Endpoint

```
GET /xsw/api/search
```

## Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | Yes | - | Search query (minimum 1 character) |
| `search_type` | string | No | `all` | Search scope: `all`, `books`, `chapters`, `content` |
| `limit` | integer | No | `20` | Maximum results to return (1-100) |

### Search Types

- **`all`**: Search everything (books + chapters + content)
- **`books`**: Search only book names and authors
- **chapters**: Search only chapter titles
- **`content`**: Search only chapter content (full-text)

## Response Format

```json
{
  "query": "search term",
  "search_type": "all",
  "total_results": 15,
  "total_books": 5,
  "results": [
    {
      "book_id": "1721851",
      "book_name": "我的老婆是魔教教主",
      "author": "作者名",
      "matches": [
        {
          "match_type": "book_name",
          "match_context": "我的老婆是魔教教主",
          "chapter_num": null,
          "chapter_title": null,
          "relevance_score": 100
        },
        {
          "match_type": "chapter_title",
          "match_context": "第123章 魔教現身",
          "chapter_num": 123,
          "chapter_title": "第123章 魔教現身",
          "relevance_score": 60
        },
        {
          "match_type": "chapter_content",
          "match_context": "...主角在魔教總部發現了驚人的秘密...",
          "chapter_num": 150,
          "chapter_title": "第150章 秘密揭曉",
          "relevance_score": 40
        }
      ]
    }
  ]
}
```

## Match Types

Results are categorized by where the match was found:

| Match Type | Description | Relevance Score |
|------------|-------------|-----------------|
| `book_name` | Match in book title | 100 (highest) |
| `author` | Match in author name | 80 |
| `chapter_title` | Match in chapter title | 60 |
| `chapter_content` | Match in chapter text | 40 |

## Relevance Scoring

Results are automatically sorted by relevance:
1. **Book name matches** (score: 100) - Most relevant
2. **Author matches** (score: 80)
3. **Chapter title matches** (score: 60)
4. **Content matches** (score: 40)

Within the same score, results are sorted alphabetically by book name.

## Features

### 1. **Smart Snippet Extraction**

For content matches, the API extracts a snippet of ~100 characters around the matched text:

```json
{
  "match_type": "chapter_content",
  "match_context": "...主角突然發現魔教教主就在眼前，他震驚地..."
}
```

### 2. **Grouped Results**

Results are grouped by book, making it easy to see all matches within the same book:

```json
{
  "book_id": "1721851",
  "book_name": "我的老婆是魔教教主",
  "matches": [
    // All matches for this book
  ]
}
```

### 3. **Case-Insensitive Search**

Search is case-insensitive using SQLite's `ILIKE` operator:
- Searching "魔教" matches "魔教", "魔教教主", etc.

### 4. **Database-First**

Search only queries the cached database, ensuring fast responses:
- No web scraping during search
- Only searches cached books and chapters
- Use background sync to populate database

## Examples

### Search Everything

```bash
curl "http://localhost:8000/xsw/api/search?q=魔教"
```

Response includes matches in book names, authors, chapter titles, and content.

### Search Only Books

```bash
curl "http://localhost:8000/xsw/api/search?q=魔教&search_type=books"
```

Only returns books where the name or author contains "魔教".

### Search Only Chapter Titles

```bash
curl "http://localhost:8000/xsw/api/search?q=秘密&search_type=chapters"
```

Returns chapters with "秘密" in the title.

### Search Chapter Content

```bash
curl "http://localhost:8000/xsw/api/search?q=驚天秘密&search_type=content"
```

Full-text search in chapter content with context snippets.

### Limit Results

```bash
curl "http://localhost:8000/xsw/api/search?q=魔教&limit=10"
```

Returns maximum 10 results.

## Use Cases

### 1. **Find Books by Name**

```bash
GET /xsw/api/search?q=魔教教主&search_type=books
```

Quickly locate books with specific keywords in the title.

### 2. **Find Books by Author**

```bash
GET /xsw/api/search?q=作者名&search_type=books
```

Search for all books by a specific author.

### 3. **Find Specific Chapters**

```bash
GET /xsw/api/search?q=第一百章&search_type=chapters
```

Locate chapters by their titles.

### 4. **Content Search**

```bash
GET /xsw/api/search?q=主角覺醒&search_type=content
```

Find chapters containing specific plot points or keywords.

### 5. **Combined Search**

```bash
GET /xsw/api/search?q=魔教&search_type=all&limit=50
```

Search across all fields for comprehensive results.

## Performance Considerations

### Database Indexing

The database has indexes on:
- `books.name` - Fast book name search
- `books.author` - Fast author search
- `chapters.title` - Fast chapter title search
- `chapters.book_id, chapters.chapter_num` - Fast chapter lookup

### Content Search Performance

Full-text content search (`search_type=content`) may be slower for:
- Large databases (many cached chapters)
- Complex queries

**Recommendations:**
- Use specific search types when possible
- Limit results appropriately
- Consider using more specific queries

### Cached Data Only

Search **only** queries the database:
- Books must be cached via background sync or user access
- Chapters must be loaded at least once
- Recently scraped data is more likely to appear

## Integration Example

### Frontend Integration

```typescript
// search.ts
import { api } from 'src/boot/axios'

interface SearchParams {
  q: string
  search_type?: 'all' | 'books' | 'chapters' | 'content'
  limit?: number
}

export async function searchBooks(params: SearchParams) {
  const { data } = await api.get('/search', { params })
  return data
}

// Usage
const results = await searchBooks({
  q: '魔教',
  search_type: 'all',
  limit: 20
})

console.log(`Found ${results.total_books} books with ${results.total_results} matches`)
results.results.forEach(book => {
  console.log(`${book.book_name} by ${book.author}`)
  book.matches.forEach(match => {
    console.log(`  - ${match.match_type}: ${match.match_context}`)
  })
})
```

## Error Handling

### Invalid Query

```bash
GET /xsw/api/search?q=
```

Response: `422 Unprocessable Entity`
```json
{
  "detail": [
    {
      "loc": ["query", "q"],
      "msg": "ensure this value has at least 1 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

### Invalid Search Type

```bash
GET /xsw/api/search?q=test&search_type=invalid
```

The API will treat it as `all` (no error, just defaults).

### Database Error

```bash
GET /xsw/api/search?q=test
```

Response: `500 Internal Server Error`
```json
{
  "detail": "Search failed: <error message>"
}
```

## Limitations

1. **Database Only**: Only searches cached data, not live web scraping
2. **No Fuzzy Matching**: Exact substring matching only (no typo tolerance)
3. **No Ranking by Frequency**: All matches of same type have same score
4. **SQLite LIKE Performance**: Large databases may have slower content search
5. **Chinese Tokenization**: No word segmentation, searches exact substrings

## Future Enhancements

Potential improvements:

1. **Full-Text Search (FTS5)**: Use SQLite FTS5 for faster content search
2. **Fuzzy Matching**: Implement Levenshtein distance for typo tolerance
3. **Ranking by Frequency**: Score results by number of matches
4. **Highlighting**: Return matched text with HTML highlighting
5. **Pagination**: Add offset/page parameters for large result sets
6. **Search History**: Track popular searches for recommendations
7. **Chinese Tokenization**: Better handling of Chinese text segmentation
8. **Autocomplete**: Suggest queries as user types

## Testing

### Manual Testing

```bash
# Search for everything
curl "http://localhost:8000/xsw/api/search?q=魔教" | jq

# Search only books
curl "http://localhost:8000/xsw/api/search?q=魔教&search_type=books" | jq

# Search with limit
curl "http://localhost:8000/xsw/api/search?q=主角&limit=5" | jq

# Search chapter content
curl "http://localhost:8000/xsw/api/search?q=秘密&search_type=content" | jq
```

### Expected Behavior

1. Empty query → 422 error
2. No matches → Empty results array
3. Valid query → Grouped results with relevance scores
4. Content matches → Snippets with ellipsis

## Monitoring

Check search performance:

```bash
# View logs
docker logs xsw | grep "\[Search\]"

# Common log messages
[Search] Error: <error details>  # Search failed
```

## Summary

The comprehensive search API provides:
- ✅ Multi-field search (books, chapters, content)
- ✅ Relevance scoring
- ✅ Grouped results by book
- ✅ Context snippets for content matches
- ✅ Flexible search types
- ✅ Fast database-only queries
- ✅ Easy integration

Use this API to build powerful search features in your novel reading application!
