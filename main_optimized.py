# main_optimized.py
"""
Optimized FastAPI backend with SQLite database-first caching.
Strategy: Check DB → Fetch from web → Store to DB
"""
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import os
import urllib3
from sqlalchemy.orm import Session

# Import our refactored modules
from db_models import init_database, get_db_session
from cache_manager import (
    init_cache_manager,
    cache_manager,
    BookInfo,
    ChapterRef,
    ChapterContent,
)
from parser import (
    extract_text_by_id,
    parse_book_info,
    fetch_chapters_from_liebiao,
    find_categories_from_nav,
    parse_books,
    extract_book_id_from_url,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------
# Configuration
# -----------------------
BASE_URL = os.getenv("BASE_URL", "https://m.xsw.tw")
DEFAULT_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))
DB_PATH = os.getenv("DB_PATH", "xsw_cache.db")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "900"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)


# -----------------------
# Helper Functions
# -----------------------
def canonical_base() -> str:
    """Return the canonical scheme+host."""
    from urllib.parse import urlparse
    p = urlparse(BASE_URL)
    return f"{p.scheme}://{p.netloc}"


def resolve_book_home(book_id: str) -> str:
    """Resolve book home URL."""
    base = canonical_base()
    if "m.xsw.tw" in base:
        return f"{base}/{book_id}/"
    else:
        return f"{base}/book/{book_id}/"


def fetch_html(url: str) -> str:
    """Fetch HTML with encoding detection."""
    resp = session.get(url, timeout=DEFAULT_TIMEOUT, verify=False)
    resp.raise_for_status()
    enc = resp.apparent_encoding or resp.encoding or "utf-8"
    resp.encoding = enc
    return resp.text


# -----------------------
# Pydantic Models
# -----------------------
class Category(BaseModel):
    id: str
    name: str
    url: str


class BookSummary(BaseModel):
    bookname: str
    author: str
    lastchapter: str
    intro: str
    bookurl: str
    book_id: Optional[str] = None


# -----------------------
# FastAPI App
# -----------------------
app = FastAPI(
    title="小說網 API (Optimized)",
    version="2.0.0",
    root_path="/xsw/api",
    description="Optimized API with SQLite database-first caching"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount SPA
spa_dir = "/app/dist/spa"
if os.path.exists(spa_dir):
    app.mount("/spa", StaticFiles(directory=spa_dir), name="spa")


# -----------------------
# Startup/Shutdown
# -----------------------
@app.on_event("startup")
async def startup_event():
    """Initialize database and cache on startup."""
    print(f"[App] Starting with BASE_URL={BASE_URL}, DB_PATH={DB_PATH}")
    init_database(f"sqlite:///{DB_PATH}")
    init_cache_manager(ttl_seconds=CACHE_TTL)
    print("[App] Database and cache initialized")


# -----------------------
# Routes
# -----------------------
@app.get("/health")
def health():
    """Health check with cache stats."""
    stats = cache_manager.get_stats() if cache_manager else {}
    return {
        "status": "ok",
        "base_url": BASE_URL,
        "db_path": DB_PATH,
        "cache_stats": stats,
    }


@app.get("/categories", response_model=List[Category])
def get_categories():
    """Get categories from homepage."""
    try:
        home_url = BASE_URL + "/"
        html_content = fetch_html(home_url)
        cats = find_categories_from_nav(html_content, BASE_URL)
        return [Category(**c) for c in cats]
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/categories/{cat_id}/books", response_model=List[BookSummary])
def list_books_in_category(cat_id: int, page: int = Query(1, ge=1)):
    """List books in category (not cached, real-time)."""
    try:
        url = f"{BASE_URL}/fenlei{cat_id}_{page}.html"
        html_content = fetch_html(url)
        books = parse_books(html_content, BASE_URL)
        return [
            BookSummary(**b, book_id=extract_book_id_from_url(b["bookurl"]))
            for b in books
        ]
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/books/{book_id}", response_model=BookInfo)
def get_book_info(book_id: str):
    """
    Get book metadata.
    Strategy: Check DB → Fetch from web → Store to DB
    """
    try:
        # Check cache first
        cached_info = cache_manager.get_book_info(book_id)
        if cached_info:
            print(f"[API] Book {book_id} - cache hit")
            return cached_info

        # Cache miss - fetch from web
        print(f"[API] Book {book_id} - cache miss, fetching from web")
        url = resolve_book_home(book_id)
        html_content = fetch_html(url)
        info = parse_book_info(html_content, BASE_URL)

        if not info:
            raise HTTPException(status_code=404, detail="Book info not found")

        info["book_id"] = book_id
        info["source_url"] = url

        # Store to cache (DB + memory)
        cache_manager.store_book_info(book_id, info)

        return BookInfo(**info)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/books/{book_id}/chapters", response_model=List[ChapterRef])
def get_book_chapters(book_id: str, nocache: bool = Query(False)):
    """
    Get chapter list for a book.
    Strategy: Check DB → Fetch from web → Store to DB
    """
    try:
        if not nocache:
            # Check if we have chapters in DB
            chapters = cache_manager.get_chapter_list(book_id)
            if chapters:
                print(f"[API] Chapters for {book_id} - DB hit ({len(chapters)} chapters)")
                return chapters

        # Cache miss or nocache - fetch from web
        print(f"[API] Chapters for {book_id} - fetching from web")
        home_url = resolve_book_home(book_id)
        html_content = fetch_html(home_url)
        items = fetch_chapters_from_liebiao(html_content, home_url, canonical_base())

        if not items:
            raise HTTPException(status_code=404, detail="No chapters found")

        # Store to DB
        cache_manager.store_chapter_refs(book_id, items)

        # Return as ChapterRef list
        return [
            ChapterRef(number=item["number"], title=item["title"], url=item["url"])
            for item in items
            if item.get("number") is not None
        ]
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/books/{book_id}/chapters/{chapter_num}", response_model=ChapterContent)
def get_chapter_content(
    book_id: str,
    chapter_num: int,
    nocache: bool = Query(False),
):
    """
    Get chapter content.
    Strategy: Check DB → Fetch from web → Store to DB
    """
    try:
        if not nocache:
            # Check cache first
            cached_content = cache_manager.get_chapter_content(book_id, chapter_num)
            if cached_content:
                print(f"[API] Chapter {book_id}:{chapter_num} - cache hit")
                return cached_content

        # Cache miss - need to fetch
        print(f"[API] Chapter {book_id}:{chapter_num} - cache miss, fetching from web")

        # First, get chapter list to find URL
        home_url = resolve_book_home(book_id)
        home_html = fetch_html(home_url)
        items = fetch_chapters_from_liebiao(home_html, home_url, canonical_base())

        # Find target chapter
        target = next((it for it in items if it.get("number") == chapter_num), None)
        if not target:
            raise HTTPException(
                status_code=404, detail=f"Chapter {chapter_num} not found"
            )

        # Fetch chapter content
        chapter_html = fetch_html(target["url"])
        text = (
            extract_text_by_id(chapter_html, "nr1")
            or extract_text_by_id(chapter_html, "nr")
            or extract_text_by_id(chapter_html, "content")
        )

        if not text:
            raise HTTPException(
                status_code=404, detail=f"No content found in {target['url']}"
            )

        # Store to cache (DB + memory)
        content_data = {
            "title": target["title"],
            "url": target["url"],
            "text": text,
        }
        cache_manager.store_chapter_content(book_id, chapter_num, content_data)

        return ChapterContent(
            book_id=book_id,
            chapter_num=chapter_num,
            title=target["title"],
            url=target["url"],
            text=text,
        )
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search", response_model=List[BookSummary])
def search_books(q: str = Query(..., min_length=1), page: int = Query(1, ge=1)):
    """Simple keyword search on category page."""
    cat_id = 2  # Default category
    try:
        url = f"{BASE_URL}/fenlei{cat_id}_{page}.html"
        html_content = fetch_html(url)
        books = parse_books(html_content, BASE_URL)
        filtered = [
            BookSummary(**b, book_id=extract_book_id_from_url(b["bookurl"]))
            for b in books
            if (q.lower() in b["bookname"].lower())
            or (q.lower() in b["author"].lower())
            or (q.lower() in b["intro"].lower())
        ]
        return filtered
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------
# Admin Endpoints
# -----------------------
@app.post("/admin/cache/clear")
def clear_memory_cache():
    """Clear in-memory cache (DB remains intact)."""
    cache_manager.clear_memory_cache()
    return {"status": "cleared", "message": "Memory cache cleared"}


@app.post("/admin/cache/invalidate/{book_id}")
def invalidate_book_cache(book_id: str):
    """Invalidate cache for a specific book."""
    cache_manager.invalidate_book(book_id)
    return {"status": "invalidated", "book_id": book_id}


@app.get("/admin/stats")
def get_cache_stats():
    """Get detailed cache statistics."""
    return cache_manager.get_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
