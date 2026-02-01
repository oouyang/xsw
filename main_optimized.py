# main_optimized.py
"""
Optimized FastAPI backend with SQLite database-first caching.
Strategy: Check DB → Fetch from web → Store to DB
"""
import re
import asyncio
from typing import List, Optional
from contextlib import asynccontextmanager
from datetime import datetime
from db_models import init_database
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Request, Depends, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import requests
import os
import shutil
import uuid
from pathlib import Path
import urllib3

# Import OpenCC for Chinese conversion
try:
    from opencc import OpenCC
    cc = OpenCC('s2t')  # Simplified to Traditional
except ImportError:
    cc = None
    print("[WARNING] opencc-python-reimplemented not installed, CN->TW search conversion disabled")

# Import our refactored modules
import cache_manager as cache_mgr
from cache_manager import (
    init_cache_manager,
    BookInfo,
    ChapterRef,
    ChapterContent,
)
from parser import (
    extract_text_by_id,
    extract_chapter_title,
    chapter_title_to_number,
    parse_book_info,
    fetch_chapters_from_liebiao,
    find_categories_from_nav,
    parse_books,
    extract_book_id_from_url,
)
import email_sender
from email_sender import init_email_sender
from rate_limiter import RateLimiter
from auth import (
    verify_google_token,
    create_jwt_token,
    verify_password,
    hash_password,
    AuthResponse,
    require_admin_auth,
    TokenPayload,
    JWT_EXPIRATION_HOURS
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------
# Configuration
# -----------------------
BASE_URL = os.getenv("BASE_URL", "https://m.xsw.tw")
WWW_BASE = os.getenv("WWW_BASE", "https://www.xsw.tw")
DEFAULT_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))
DB_PATH = os.getenv("DB_PATH", "xsw_cache.db")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "900"))

# Rate limiting configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_WHITELIST = os.getenv("RATE_LIMIT_WHITELIST", "127.0.0.1,::1").split(",")

# Use default Python requests User-Agent instead of browser-like UA
# This helps with corporate proxies like Zscaler that may block browser UAs
# but allow automated tool requests
session = requests.Session()
# Don't set custom headers - use default requests User-Agent


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
    # Use verify=False to bypass SSL verification with corporate proxy/Zscaler
    # The proxy does SSL inspection and we don't have their CA cert in container
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
    lasturl: str
    intro: str
    bookurl: str
    book_id: Optional[str] = None


# -----------------------
# FastAPI App with Lifespan
# -----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup: Initialize database and cache
    print(f"[App] Starting with BASE_URL={BASE_URL}, DB_PATH={DB_PATH}")
    init_database(f"sqlite:///{DB_PATH}")
    init_cache_manager(ttl_seconds=CACHE_TTL)

    # Initialize admin users
    from auth import init_admin_users
    import db_models
    if db_models.db_manager:
        init_admin_users(db_models.db_manager)

    print("[App] Database, cache, and auth initialized")

    yield  # Application runs here

    # Shutdown: Cleanup
    print("[App] Shutting down...")
    print("[App] Shutdown complete")

app = FastAPI(
    title="看小說 API (Optimized)",
    version="2.0.0",
    description="Optimized API with SQLite database-first caching",
    lifespan=lifespan
)

# Create API router for all API endpoints
api_router = APIRouter()

# -----------------------
# Rate Limiting Middleware
# -----------------------
# Initialize rate limiter
rate_limiter = RateLimiter(RATE_LIMIT_WHITELIST) if RATE_LIMIT_ENABLED else None

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply progressive rate limiting per client IP"""

    async def dispatch(self, request: Request, call_next):
        if not RATE_LIMIT_ENABLED or rate_limiter is None:
            return await call_next(request)

        # Extract client IP (support X-Forwarded-For for proxies)
        client_ip = request.headers.get("X-Forwarded-For")
        if client_ip:
            # X-Forwarded-For can be comma-separated list, take first
            client_ip = client_ip.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        # Get delay based on current request count
        delay = rate_limiter.get_delay(client_ip)

        # Apply delay if needed
        if delay > 0:
            request_count = len(rate_limiter._request_history.get(client_ip, [])) + 1
            print(f"[RateLimit] Client {client_ip} has {request_count} requests in last 60s - applying {delay}s delay")
            await asyncio.sleep(delay)

        # Record this request
        rate_limiter.record_request(client_ip)

        # Process request
        response = await call_next(request)
        return response

# Add rate limiting middleware before CORS (so it runs first)
if RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware)
    print(f"[App] Rate limiting enabled with whitelist: {RATE_LIMIT_WHITELIST}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add simple health check at root level (for monitoring)
@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}

# Mount SPA static files (assets, js, css)
spa_dir = "/app/dist/spa"
# spa_index_html = os.path.join(spa_dir, "index.html") if os.path.exists(spa_dir) else None

if os.path.exists(spa_dir):
    INDEX_FILE = Path(spa_dir) / "index.html"

    # 1) Serve / (and /index.html) explicitly
    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(INDEX_FILE, media_type="text/html")

    # 2) Mount static assets at /assets (avoid mounting at root which catches all paths)
    assets_dir = os.path.join(spa_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # 3) Mount icons
    icons_dir = os.path.join(spa_dir, "icons")
    if os.path.exists(icons_dir):
        app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

    # 4) Serve other root-level static files manually
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return FileResponse(os.path.join(spa_dir, "favicon.ico"))

    @app.get("/{filename}.{ext}", include_in_schema=False)
    async def spa_static_files(filename: str, ext: str):
        """Serve static files like config.json, opc.pem, etc."""
        filepath = os.path.join(spa_dir, f"{filename}.{ext}")
        if os.path.exists(filepath) and os.path.isfile(filepath):
            return FileResponse(filepath)
        raise HTTPException(status_code=404, detail="File not found")

    # 5) SPA history-mode fallback:
    #    - Only for paths under "/" that are NOT API calls and NOT obvious assets
    @app.middleware("http")
    async def spa_history_mode_fallback(request: Request, call_next):
        # Let normal routing/StaticFiles try first (APIs, real files, etc.)
        response: Response = await call_next(request)

        if response.status_code != 404:
            return response

        path = request.url.path or ""

        # DO NOT touch API paths (these are handled by routers behind root_path)
        # Externally, APIs are /xsw/api/**, but internally Starlette still sees paths
        # without root_path. If you also mount/route with "/xsw/api" prefixes locally,
        # keep this guard; otherwise you can remove it.
        if path.startswith("/xsw/api"):
            return response

        # Heuristic: if the last segment has no dot => likely a client route, not a file.
        last_seg = path.rsplit("/", 1)[-1]
        if "." not in last_seg and INDEX_FILE.exists():
            return FileResponse(INDEX_FILE, media_type="text/html")

        # For missing real files, keep 404
        return response

# -----------------------
# API Routes
# -----------------------
@api_router.get("/health")
def health():
    """Health check with cache stats."""
    cache_stats = cache_mgr.cache_manager.get_stats() if cache_mgr.cache_manager else {}
    return {
        "status": "ok",
        "base_url": BASE_URL,
        "db_path": DB_PATH,
        "cache_stats": cache_stats,
    }


@api_router.get("/categories", response_model=List[Category])
def get_categories():
    """Get categories from homepage."""
    try:
        home_url = BASE_URL + "/"
        print(f"[API] Fetching categories from {home_url}")
        html_content = fetch_html(home_url)
        print(f"[API] Got HTML, length: {len(html_content)}")
        # Save HTML to file for debugging
        debug_file = "/tmp/categories_debug.html"
        with open(debug_file, "w") as f:
            f.write(html_content)
        print(f"[API] Saved HTML to {debug_file}")
        # Check if HTML contains fenlei links
        import re
        fenlei_matches = re.findall(r"fenlei\d+_1\.html", html_content)
        print(f"[API] Found {len(fenlei_matches)} fenlei matches in HTML")
        if fenlei_matches:
            print(f"[API] First 5 matches: {fenlei_matches[:5]}")
        cats = find_categories_from_nav(html_content, BASE_URL)
        print(f"[API] Found {len(cats)} categories")
        if cats:
            print(f"[API] First category: {cats[0]}")
        result = [Category(**c) for c in cats]
        print(f"[API] Returning {len(result)} Category objects")
        return result
    except requests.HTTPError as e:
        print(f"[API] HTTP Error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        print(f"[API] Exception: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/categories/{cat_id}/books", response_model=List[BookSummary])
def list_books_in_category(
    cat_id: int,
    page: int = Query(1, ge=1),
):
    """List books in category (not cached, real-time)."""
    try:
        url = f"{BASE_URL}/fenlei{cat_id}_{page}.html"
        html_content = fetch_html(url)
        books = parse_books(html_content, BASE_URL)

        book_summaries = [
            BookSummary(**b, book_id=extract_book_id_from_url(b["bookurl"]))
            for b in books
        ]

        return book_summaries
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/books/{book_id}", response_model=BookInfo)
def get_book_info(book_id: str):
    """
    Get book metadata.
    Strategy: Check DB → Fetch from web → Store to DB
    """
    try:
        # Check cache first
        cached_info = cache_mgr.cache_manager.get_book_info(book_id)
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
        cache_mgr.cache_manager.store_book_info(book_id, info)

        return BookInfo(**info)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/books/{book_id}/chapters", response_model=List[ChapterRef])
def get_book_chapters(
    book_id: str,
    page: int = Query(1, ge=1),
    nocache: bool = Query(False),
    www: bool = Query(False),
    all_chapters_flag: bool = Query(False, alias="all")
):
    """
    Get chapter list for a book.
    Strategy: Check DB → Fetch from web → Store to DB

    - www=true: Fetch from home page only (latest ~10 chapters)
    - www=false (default): Fetch from pagination pages (all chapters)
    - all=true: Return all chapters
    - all=false: Return server-side paginated slice (20 chapters per page)
    - page: Page number for server-side pagination (when all=false)
    """
    try:
        # First, try to get all chapters from DB or web
        all_chapters = None

        if not nocache:
            # Check if we have chapters in DB
            all_chapters = cache_mgr.cache_manager.get_chapter_list(book_id)
            if all_chapters:
                print(f"[API] Chapters for {book_id} - DB hit ({len(all_chapters)} chapters)")

        if not all_chapters:
            # Cache miss or nocache - fetch from web
            print(f"[API] Chapters for {book_id} - fetching from web (www={www})")

            if www:
                # Fetch from home page only (mobile site - latest 10 chapters)
                # NOTE: Don't cache these results as they may be partial and incorrectly numbered
                home_url = resolve_book_home(book_id)
                html_content = fetch_html(home_url)
                items = fetch_chapters_from_liebiao(html_content, home_url, canonical_base(), start_index=1)
            else:
                # Fetch from pagination pages (all chapters)
                items = fetch_all_chapters_from_pagination(book_id)

            if not items:
                raise HTTPException(status_code=404, detail="No chapters found")

            # Store to DB only for full fetches (www=false)
            # Partial fetches (www=true) from home page may be incorrectly numbered
            if not www:
                cache_mgr.cache_manager.store_chapter_refs(book_id, items)

            # Convert to ChapterRef list
            all_chapters = [
                ChapterRef(number=item["number"], title=item["title"], url=item["url"])
                for item in items
                if item.get("number") is not None
            ]

            # CRITICAL: Sort chapters by number to ensure correct order
            # HTML may return chapters out of order
            all_chapters.sort(key=lambda c: c.number)
            print(f"[API] Sorted {len(all_chapters)} chapters by number")

            # Sync book info with actual last chapter from fetched chapters
            # Only do this for full fetches (www=false) as partial fetches may have incorrect numbering
            if all_chapters and not www:
                last_chapter = max(all_chapters, key=lambda c: c.number)
                print(f"[API] Syncing book {book_id} with last chapter: {last_chapter.number} - {last_chapter.title}")

                # Get or create book info
                book_info = cache_mgr.cache_manager.get_book_info(book_id)
                if book_info:
                    # Update existing book info
                    book_info_dict = book_info.dict()
                    book_info_dict["last_chapter_number"] = last_chapter.number
                    book_info_dict["last_chapter_title"] = last_chapter.title
                    book_info_dict["last_chapter_url"] = last_chapter.url
                    cache_mgr.cache_manager.store_book_info(book_id, book_info_dict)
                    print(f"[API] Updated book {book_id} last_chapter_number to {last_chapter.number}")
                else:
                    # Book info not in cache - fetch and update it
                    try:
                        url = resolve_book_home(book_id)
                        html_content = fetch_html(url)
                        info = parse_book_info(html_content, BASE_URL)
                        if info:
                            info["book_id"] = book_id
                            info["source_url"] = url
                            info["last_chapter_number"] = last_chapter.number
                            info["last_chapter_title"] = last_chapter.title
                            info["last_chapter_url"] = last_chapter.url
                            cache_mgr.cache_manager.store_book_info(book_id, info)
                            print(f"[API] Created book info for {book_id} with last_chapter_number: {last_chapter.number}")
                    except Exception as e:
                        print(f"[API] Warning: Failed to fetch book info during sync: {e}")

        # Return based on 'all' parameter
        if all_chapters_flag:
            # Return all chapters
            return all_chapters

        # Server-side pagination: slice the results
        CHAPTERS_PAGE_SIZE = 20
        total_chapters = len(all_chapters)
        total_pages = max(1, (total_chapters + CHAPTERS_PAGE_SIZE - 1) // CHAPTERS_PAGE_SIZE)
        current_page = min(max(page, 1), total_pages)

        start_idx = (current_page - 1) * CHAPTERS_PAGE_SIZE
        end_idx = start_idx + CHAPTERS_PAGE_SIZE
        page_chapters = all_chapters[start_idx:end_idx]

        print(f"[API] Returning page {current_page}/{total_pages} ({len(page_chapters)} chapters)")
        return page_chapters

    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def fetch_all_chapters_from_pagination(book_id: str) -> list:
    """
    Fetch all chapters by scanning pagination pages.
    Mobile site uses /book_id/page-N.html format.
    """
    from bs4 import BeautifulSoup
    import re

    base = canonical_base()

    # Start with page 1
    page_url = f"{base}/{book_id}/page-1.html"
    html_content = fetch_html(page_url)

    # Get total pages from pagination info
    soup = BeautifulSoup(html_content, "html.parser")
    page_divs = soup.find_all("div", class_="page")
    total_pages = 1

    # Try both page divs (there are usually 2)
    for page_div in page_divs:
        text = page_div.get_text(strip=True)
        print(f"[API] DEBUG: Checking page div text: '{text[:100]}'")

        # Try multiple patterns to match pagination
        # Pattern 1: (第1/71頁) - with parentheses
        m = re.search(r"\(第\d+/(\d+)頁\)", text)
        if m:
            total_pages = int(m.group(1))
            print(f"[API] Detected {total_pages} pages from pattern 1: {text[:50]}")
            break

        # Pattern 2: 第1/71頁 - without parentheses
        m = re.search(r"第\d+/(\d+)頁", text)
        if m:
            total_pages = int(m.group(1))
            print(f"[API] Detected {total_pages} pages from pattern 2: {text[:50]}")
            break

        # Pattern 3: Look for "尾頁" (last page) link to extract page number
        last_page_link = page_div.find("a", string=re.compile("尾頁"))
        if not last_page_link:
            last_page_link = page_div.find("a", class_="ngroup")

        if last_page_link:
            href = last_page_link.get("href", "")
            m = re.search(r"/page-(\d+)\.html", href)
            if m:
                total_pages = int(m.group(1))
                print(f"[API] Detected {total_pages} pages from last page link: {href}")
                break

    print(f"[API] Found {total_pages} pages for book {book_id}")

    # Collect all chapters from all pages with sequential indexing
    all_items = []
    current_chapter_index = 1  # Start from chapter 1
    for page_num in range(1, total_pages + 1):
        page_url = f"{base}/{book_id}/page-{page_num}.html"
        html_content = fetch_html(page_url)
        # Pass start_index to ensure sequential numbering across pages
        items = fetch_chapters_from_liebiao(html_content, page_url, base, start_index=current_chapter_index)
        all_items.extend(items)
        print(f"[API] Page {page_num}/{total_pages}: found {len(items)} chapters (indices {current_chapter_index}-{current_chapter_index + len(items) - 1})")
        # Update index for next page
        current_chapter_index += len(items)

    return all_items


@api_router.get("/books/{book_id}/chapters/{chapter_num}", response_model=ChapterContent)
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
            cached_content = cache_mgr.cache_manager.get_chapter_content(book_id, chapter_num)
            if cached_content:
                print(f"[API] Chapter {book_id}:{chapter_num} - cache hit")
                return cached_content

        # Cache miss - need to fetch
        print(f"[API] Chapter {book_id}:{chapter_num} - cache miss, fetching from web")

        # Strategy: Try to get chapter URL from DB first (fastest)
        chapter_url = get_chapter_url_from_db(book_id, chapter_num)

        if not chapter_url:
            # Chapter URL not in DB - need to fetch chapter list first
            print(f"[API] Chapter {book_id}:{chapter_num} - URL not in DB, fetching chapter list")

            # Try home page first (for recent chapters)
            home_url = resolve_book_home(book_id)
            home_html = fetch_html(home_url)
            items = fetch_chapters_from_liebiao(home_html, home_url, canonical_base(), start_index=1)

            # Find target chapter in home page
            target = next((it for it in items if it.get("number") == chapter_num), None)

            if not target:
                # Not in home page - fetch all chapters from pagination
                print(f"[API] Chapter {chapter_num} not in home page, fetching all chapters")
                items = fetch_all_chapters_from_pagination(book_id)

                # Store all chapters to DB for future use
                cache_mgr.cache_manager.store_chapter_refs(book_id, items)

                # Find target chapter
                target = next((it for it in items if it.get("number") == chapter_num), None)
                if not target:
                    raise HTTPException(
                        status_code=404, detail=f"Chapter {chapter_num} not found"
                    )

            chapter_url = target["url"]
            chapter_title = target["title"]
        else:
            # Got URL from DB - get title too
            chapter_title = get_chapter_title_from_db(book_id, chapter_num) or f"Chapter {chapter_num}"
            print(f"[API] Chapter {book_id}:{chapter_num} - found URL in DB: {chapter_url}")

        # Fetch chapter content
        chapter_html = fetch_html(chapter_url)
        text = (
            extract_text_by_id(chapter_html, "nr1")
            or extract_text_by_id(chapter_html, "nr")
            or extract_text_by_id(chapter_html, "content")
        )

        if not text:
            raise HTTPException(
                status_code=404, detail=f"No content found in {chapter_url}"
            )

        # Store to cache (DB + memory)
        content_data = {
            "title": chapter_title,
            "url": chapter_url,
            "text": text,
        }
        cache_mgr.cache_manager.store_chapter_content(book_id, chapter_num, content_data)

        return ChapterContent(
            book_id=book_id,
            chapter_num=chapter_num,
            title=chapter_title,
            url=chapter_url,
            text=text,
        )
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_chapter_url_from_db(book_id: str, chapter_num: int) -> Optional[str]:
    """Get chapter URL from database if it exists."""
    try:
        from db_models import Chapter
        import db_models

        if not db_models.db_manager:
            return None

        session = db_models.db_manager.get_session()
        try:
            chapter = (
                session.query(Chapter)
                .filter(Chapter.book_id == book_id, Chapter.chapter_num == chapter_num)
                .first()
            )
            return chapter.url if chapter else None
        finally:
            session.close()
    except Exception as e:
        print(f"[API] Error getting chapter URL from DB: {e}")
        return None


def get_chapter_title_from_db(book_id: str, chapter_num: int) -> Optional[str]:
    """Get chapter title from database if it exists."""
    try:
        from db_models import Chapter
        import db_models

        if not db_models.db_manager:
            return None

        session = db_models.db_manager.get_session()
        try:
            chapter = (
                session.query(Chapter)
                .filter(Chapter.book_id == book_id, Chapter.chapter_num == chapter_num)
                .first()
            )
            return chapter.title if chapter else None
        finally:
            session.close()
    except Exception as e:
        print(f"[API] Error getting chapter title from DB: {e}")
        return None


class SearchResult(BaseModel):
    """Search result with match context."""
    book_id: str
    book_name: str
    author: Optional[str] = None
    match_type: str  # 'book_name', 'author', 'chapter_title', 'chapter_content'
    match_context: Optional[str] = None  # Snippet of matched text
    chapter_num: Optional[int] = None
    chapter_title: Optional[str] = None
    relevance_score: int = 0  # Higher = more relevant


def _extract_snippet(text: str, query: str, context_chars: int = 100) -> str:
    """Extract a snippet of text around the search query."""
    query_lower = query.lower()
    text_lower = text.lower()

    # Find the first occurrence
    pos = text_lower.find(query_lower)
    if pos == -1:
        return text[:context_chars] + "..." if len(text) > context_chars else text

    # Calculate snippet boundaries
    start = max(0, pos - context_chars // 2)
    end = min(len(text), pos + len(query) + context_chars // 2)

    snippet = text[start:end]

    # Add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


@api_router.get("/search")
def search_comprehensive(
    q: str = Query(..., min_length=1, description="Search query"),
    search_type: str = Query("all", description="Search scope: all, books, chapters, content"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
):
    """
    Comprehensive search across books, chapter titles, and chapter content.

    Search types:
    - all: Search everything (books + chapters + content)
    - books: Search only book names and authors
    - chapters: Search only chapter titles
    - content: Search only chapter content (full-text search)

    Returns grouped results with relevance scoring.

    Note: Automatically converts Simplified Chinese (CN) to Traditional Chinese (TW)
    since the database content is in Traditional Chinese.
    """
    try:
        # Convert CN to TW if converter is available
        search_query = q
        if cc is not None:
            try:
                search_query_tw = cc.convert(q)
                print(f"[Search] Converted query: '{q}' -> '{search_query_tw}'")
                search_query = search_query_tw
            except Exception as e:
                print(f"[Search] Conversion failed: {e}, using original query")
                search_query = q

        query_lower = search_query.lower()
        results: List[SearchResult] = []

        # Search in database first
        session = cache_mgr.cache_manager._get_session()

        try:
            # 1. Search Books (name and author)
            if search_type in ["all", "books"]:
                from db_models import Book
                books = (
                    session.query(Book)
                    .filter(
                        (Book.name.like(f"%{search_query}%")) | (Book.author.like(f"%{search_query}%"))
                    )
                    .limit(limit)
                    .all()
                )

                for book in books:
                    # Calculate relevance score
                    score = 0
                    match_type = None
                    match_context = None

                    if query_lower in book.name.lower():
                        score = 100  # Exact book name match highest priority
                        match_type = "book_name"
                        match_context = book.name
                    elif book.author and query_lower in book.author.lower():
                        score = 80
                        match_type = "author"
                        match_context = book.author

                    results.append(
                        SearchResult(
                            book_id=book.id,
                            book_name=book.name,
                            author=book.author,
                            match_type=match_type,
                            match_context=match_context,
                            relevance_score=score,
                        )
                    )

            # 2. Search Chapter Titles
            if search_type in ["all", "chapters"]:
                from db_models import Chapter, Book

                chapters = (
                    session.query(Chapter, Book.name, Book.author)
                    .join(Book, Chapter.book_id == Book.id)
                    .filter(Chapter.title.like(f"%{search_query}%"))
                    .limit(limit)
                    .all()
                )

                for chapter, book_name, author in chapters:
                    results.append(
                        SearchResult(
                            book_id=chapter.book_id,
                            book_name=book_name,
                            author=author,
                            match_type="chapter_title",
                            match_context=chapter.title,
                            chapter_num=chapter.chapter_num,
                            chapter_title=chapter.title,
                            relevance_score=60,
                        )
                    )

            # 3. Search Chapter Content (full-text)
            if search_type in ["all", "content"]:
                from db_models import Chapter, Book

                # Only search chapters that have content
                content_matches = (
                    session.query(Chapter, Book.name, Book.author)
                    .join(Book, Chapter.book_id == Book.id)
                    .filter(
                        Chapter.text.isnot(None),
                        Chapter.text.like(f"%{search_query}%")
                    )
                    .limit(limit)
                    .all()
                )

                for chapter, book_name, author in content_matches:
                    # Extract context snippet around the match
                    text = chapter.text or ""
                    snippet = _extract_snippet(text, search_query, context_chars=100)

                    results.append(
                        SearchResult(
                            book_id=chapter.book_id,
                            book_name=book_name,
                            author=author,
                            match_type="chapter_content",
                            match_context=snippet,
                            chapter_num=chapter.chapter_num,
                            chapter_title=chapter.title,
                            relevance_score=40,
                        )
                    )

        finally:
            session.close()

        # Sort by relevance score (highest first), then by book name
        results.sort(key=lambda x: (-x.relevance_score, x.book_name))

        # Limit results
        results = results[:limit]

        # Group results by book for better presentation
        grouped_results = {}
        for result in results:
            if result.book_id not in grouped_results:
                grouped_results[result.book_id] = {
                    "book_id": result.book_id,
                    "book_name": result.book_name,
                    "author": result.author,
                    "matches": [],
                }
            grouped_results[result.book_id]["matches"].append(
                {
                    "match_type": result.match_type,
                    "match_context": result.match_context,
                    "chapter_num": result.chapter_num,
                    "chapter_title": result.chapter_title,
                    "relevance_score": result.relevance_score,
                }
            )

        return {
            "query": q,
            "search_type": search_type,
            "total_results": len(results),
            "total_books": len(grouped_results),
            "results": list(grouped_results.values()),
        }

    except Exception as e:
        print(f"[Search] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# -----------------------
# Authentication Endpoints
# -----------------------


class GoogleAuthRequest(BaseModel):
    """Request body for Google OAuth authentication."""
    id_token: str


class PasswordAuthRequest(BaseModel):
    """Request body for password authentication."""
    email: str
    password: str


class PasswordChangeRequest(BaseModel):
    """Request body for changing password."""
    current_password: str
    new_password: str


@api_router.post("/auth/google", response_model=AuthResponse)
async def authenticate_with_google(request: GoogleAuthRequest):
    """
    Authenticate admin user with Google OAuth2 token.

    Flow:
    1. Verify Google ID token
    2. Check email whitelist
    3. Create or update AdminUser record
    4. Generate JWT token
    """
    try:
        # Verify Google token
        user_info = verify_google_token(request.id_token)

        # Get or create admin user
        import db_models
        from db_models import AdminUser

        if not db_models.db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        session = db_models.db_manager.get_session()
        try:
            admin_user = session.query(AdminUser).filter_by(
                email=user_info['email']
            ).first()

            if not admin_user:
                # Create new admin user
                admin_user = AdminUser(
                    email=user_info['email'],
                    auth_method='google',
                    google_id=user_info['google_id'],
                    picture_url=user_info['picture'],
                    is_active=True,
                    last_login_at=datetime.utcnow()
                )
                session.add(admin_user)
            else:
                # Update existing user
                admin_user.last_login_at = datetime.utcnow()
                admin_user.google_id = user_info['google_id']
                admin_user.picture_url = user_info['picture']

            session.commit()

            # Check if user is active
            if not admin_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin account is deactivated"
                )

            # Generate JWT token
            token, expiration = create_jwt_token(admin_user.email, 'google')

            return AuthResponse(
                access_token=token,
                expires_in=JWT_EXPIRATION_HOURS * 3600,
                user={
                    'email': admin_user.email,
                    'auth_method': 'google',
                    'picture': admin_user.picture_url
                }
            )
        finally:
            session.close()

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        print(f"[AUTH] Google authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


@api_router.post("/auth/password", response_model=AuthResponse)
async def authenticate_with_password(request: PasswordAuthRequest):
    """
    Authenticate admin user with email and password.
    Fallback method for emergency access.
    """
    import db_models
    from db_models import AdminUser

    if not db_models.db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    session = db_models.db_manager.get_session()
    try:
        # Find admin user
        admin_user = session.query(AdminUser).filter_by(
            email=request.email,
            auth_method='password'
        ).first()

        if not admin_user or not admin_user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Verify password
        if not verify_password(request.password, admin_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Check if user is active
        if not admin_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account is deactivated"
            )

        # Update last login
        admin_user.last_login_at = datetime.utcnow()
        session.commit()

        # Generate JWT token
        token, expiration = create_jwt_token(admin_user.email, 'password')

        return AuthResponse(
            access_token=token,
            expires_in=JWT_EXPIRATION_HOURS * 3600,
            user={
                'email': admin_user.email,
                'auth_method': 'password'
            }
        )
    finally:
        session.close()


@api_router.post("/auth/password/change")
async def change_password(
    request: PasswordChangeRequest,
    auth: TokenPayload = Depends(require_admin_auth)
):
    """
    Change admin user password (requires authentication).
    """
    import db_models
    from db_models import AdminUser

    if not db_models.db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    session = db_models.db_manager.get_session()
    try:
        # Find admin user
        admin_user = session.query(AdminUser).filter_by(
            email=auth.sub,
            auth_method='password'
        ).first()

        if not admin_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Password authentication not enabled for this user"
            )

        # Verify current password
        if not verify_password(request.current_password, admin_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )

        # Update password
        admin_user.password_hash = hash_password(request.new_password)
        session.commit()

        return {"status": "success", "message": "Password changed successfully"}
    finally:
        session.close()


@api_router.get("/auth/verify")
async def verify_token(auth: TokenPayload = Depends(require_admin_auth)):
    """
    Verify if current JWT token is valid.
    Used by frontend to check authentication status.
    """
    return {
        "valid": True,
        "email": auth.sub,
        "auth_method": auth.auth_method
    }


# -----------------------
# Admin Endpoints
# -----------------------
@api_router.post("/admin/cache/clear")
def clear_memory_cache(auth: TokenPayload = Depends(require_admin_auth)):
    """Clear in-memory cache (DB remains intact)."""
    cache_mgr.cache_manager.clear_memory_cache()
    return {"status": "cleared", "message": "Memory cache cleared"}


@api_router.post("/admin/cache/invalidate/{book_id}")
def invalidate_book_cache(book_id: str, auth: TokenPayload = Depends(require_admin_auth)):
    """Invalidate memory cache for a specific book (DB remains intact)."""
    cache_mgr.cache_manager.invalidate_book(book_id)
    return {"status": "invalidated", "book_id": book_id, "scope": "memory_only"}


@api_router.delete("/admin/cache/chapters/{book_id}")
def delete_book_chapters_cache(book_id: str, auth: TokenPayload = Depends(require_admin_auth)):
    """Delete all chapter records for a book from database and memory cache."""
    deleted_count = cache_mgr.cache_manager.delete_book_chapters(book_id)
    return {
        "status": "deleted",
        "book_id": book_id,
        "deleted_chapters": deleted_count,
        "message": f"Deleted {deleted_count} chapters from cache. Next fetch will reload from web.",
    }


@api_router.get("/admin/stats")
def get_cache_stats(auth: TokenPayload = Depends(require_admin_auth)):
    """Get detailed cache statistics."""
    return cache_mgr.cache_manager.get_stats()


@api_router.get("/admin/rate-limit/stats")
def get_rate_limit_stats(auth: TokenPayload = Depends(require_admin_auth)):
    """Get rate limiter statistics."""
    if not RATE_LIMIT_ENABLED or rate_limiter is None:
        return {"enabled": False}

    return {
        "enabled": True,
        "whitelist": RATE_LIMIT_WHITELIST,
        **rate_limiter.get_stats()
    }


# ============================================
# SMTP & Email Endpoints
# ============================================


@api_router.get("/admin/smtp/settings")
def get_smtp_settings(auth: TokenPayload = Depends(require_admin_auth)):
    """Get current SMTP settings (password masked)."""
    import db_models
    from db_models import SmtpSettings

    if not db_models.db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    session = db_models.db_manager.get_session()
    try:
        settings = session.query(SmtpSettings).filter_by(id=1).first()
        if not settings:
            return {
                "configured": False,
                "message": "SMTP not configured"
            }

        return {
            "configured": True,
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "smtp_user": settings.smtp_user,
            "smtp_password": "********" if settings.smtp_password else "",
            "use_tls": settings.use_tls,
            "use_ssl": settings.use_ssl,
            "from_email": settings.from_email,
            "from_name": settings.from_name,
            "last_test_at": settings.last_test_at.isoformat() if settings.last_test_at else None,
            "last_test_status": settings.last_test_status,
        }
    finally:
        session.close()


@api_router.post("/admin/smtp/settings")
def save_smtp_settings(
    smtp_host: str = Query(...),
    smtp_port: int = Query(...),
    smtp_user: str = Query(...),
    smtp_password: str = Query(...),
    use_tls: bool = Query(True),
    use_ssl: bool = Query(False),
    from_email: str = Query(None),
    from_name: str = Query("看小說 Admin"),
    auth: TokenPayload = Depends(require_admin_auth)
):
    """Save SMTP configuration."""
    import db_models
    from db_models import SmtpSettings
    from datetime import datetime

    if not db_models.db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    session = db_models.db_manager.get_session()
    try:
        # Get or create settings
        settings = session.query(SmtpSettings).filter_by(id=1).first()
        if not settings:
            settings = SmtpSettings(id=1)
            session.add(settings)

        # Update settings
        settings.smtp_host = smtp_host
        settings.smtp_port = smtp_port
        settings.smtp_user = smtp_user
        settings.smtp_password = smtp_password
        settings.use_tls = use_tls
        settings.use_ssl = use_ssl
        settings.from_email = from_email or smtp_user
        settings.from_name = from_name
        settings.updated_at = datetime.utcnow()

        session.commit()

        # Initialize email sender
        smtp_config = {
            'smtp_host': smtp_host,
            'smtp_port': smtp_port,
            'smtp_user': smtp_user,
            'smtp_password': smtp_password,
            'use_tls': use_tls,
            'use_ssl': use_ssl,
            'from_email': from_email or smtp_user,
            'from_name': from_name,
        }
        init_email_sender(smtp_config)

        return {
            "status": "success",
            "message": "SMTP settings saved successfully"
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save SMTP settings: {str(e)}")
    finally:
        session.close()


@api_router.post("/admin/smtp/test")
def test_smtp_connection(auth: TokenPayload = Depends(require_admin_auth)):
    """Test SMTP connection with current settings."""
    import db_models
    from db_models import SmtpSettings
    from datetime import datetime

    if not db_models.db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    session = db_models.db_manager.get_session()
    try:
        settings = session.query(SmtpSettings).filter_by(id=1).first()
        if not settings:
            raise HTTPException(status_code=404, detail="SMTP not configured")

        # Create email sender
        sender = email_sender.EmailSender(
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_password=settings.smtp_password,
            use_tls=settings.use_tls,
            use_ssl=settings.use_ssl,
            from_email=settings.from_email,
            from_name=settings.from_name,
        )

        # Test connection
        result = sender.test_connection()

        # Update last test time and status
        settings.last_test_at = datetime.utcnow()
        settings.last_test_status = result['status']
        session.commit()

        return result
    finally:
        session.close()


@api_router.post("/admin/email/send")
def send_email(
    to_email: str = Query(...),
    subject: str = Query(...),
    body: str = Query(...),
    is_html: bool = Query(False),
    cc: str = Query(None),
    bcc: str = Query(None),
    attachments: str = Query(None),
    auth: TokenPayload = Depends(require_admin_auth)
):
    """
    Send an email using configured SMTP settings.

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body
        is_html: Whether body is HTML (default: False)
        cc: Comma-separated CC email addresses
        bcc: Comma-separated BCC email addresses
        attachments: Comma-separated file paths (relative to /app/dist/spa or absolute paths)
    """
    import db_models
    from db_models import SmtpSettings

    if not email_sender.email_sender:
        # Try to initialize from database
        if not db_models.db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        session = db_models.db_manager.get_session()
        try:
            settings = session.query(SmtpSettings).filter_by(id=1).first()
            if not settings:
                raise HTTPException(status_code=404, detail="SMTP not configured")

            smtp_config = {
                'smtp_host': settings.smtp_host,
                'smtp_port': settings.smtp_port,
                'smtp_user': settings.smtp_user,
                'smtp_password': settings.smtp_password,
                'use_tls': settings.use_tls,
                'use_ssl': settings.use_ssl,
                'from_email': settings.from_email,
                'from_name': settings.from_name,
            }
            init_email_sender(smtp_config)
        finally:
            session.close()

    # Parse CC and BCC
    cc_list = [email.strip() for email in cc.split(',')] if cc else None
    bcc_list = [email.strip() for email in bcc.split(',')] if bcc else None

    # Parse attachment paths
    attachment_paths = None
    if attachments:
        attachment_paths = []
        for path in attachments.split(','):
            path = path.strip()
            if path:
                # Convert relative paths (e.g., /spa/upload/file.pdf) to absolute paths
                if path.startswith('/spa/'):
                    path = path.replace('/spa/', '/app/dist/spa/', 1)
                attachment_paths.append(path)

    # Send email
    result = email_sender.email_sender.send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        is_html=is_html,
        cc=cc_list,
        bcc=bcc_list,
        attachments=attachment_paths,
    )

    if result['status'] == 'error':
        raise HTTPException(status_code=500, detail=result['message'])

    return result


@api_router.post("/admin/upload")
async def upload_file(file: UploadFile = File(...), auth: TokenPayload = Depends(require_admin_auth)):
    """
    Upload a file to the /dist/spa/upload folder.
    Returns the URL path to access the uploaded file.
    """
    try:
        # Create upload directory if it doesn't exist
        upload_dir = Path("/app/dist/spa/upload")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename to prevent collisions
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename

        # Save the file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Return the URL path
        file_url = f"/spa/upload/{unique_filename}"

        return {
            "status": "success",
            "message": "File uploaded successfully",
            "filename": unique_filename,
            "original_filename": file.filename,
            "url": file_url,
            "size": file_path.stat().st_size
        }

    except Exception as e:
        print(f"[Upload] Failed to upload file: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@api_router.post("/admin/alert/chapter-validation")
def send_chapter_validation_alert(
    book_id: str = Query(...),
    book_name: str = Query(...),
    reason: str = Query(...),
    retries: int = Query(...),
    last_chapter_number: int = Query(0),
    actual_chapter_count: int = Query(0),
    to_email: str = Query(...),
    auth: TokenPayload = Depends(require_admin_auth)
):
    """
    Send an alert email when chapter validation fails after max retries.

    This endpoint is called by the frontend after detecting unreasonable chapters
    and exhausting retry attempts (default: 3 retries).
    """
    if not email_sender.email_sender:
        # Try to initialize from database
        import db_models
        from db_models import SmtpSettings

        if not db_models.db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        session = db_models.db_manager.get_session()
        try:
            settings = session.query(SmtpSettings).filter_by(id=1).first()
            if not settings:
                raise HTTPException(status_code=404, detail="SMTP not configured, cannot send alert email")

            smtp_config = {
                'smtp_host': settings.smtp_host,
                'smtp_port': settings.smtp_port,
                'smtp_user': settings.smtp_user,
                'smtp_password': settings.smtp_password,
                'use_tls': settings.use_tls,
                'use_ssl': settings.use_ssl,
                'from_email': settings.from_email,
                'from_name': settings.from_name,
            }
            init_email_sender(smtp_config)
        finally:
            session.close()

    # Build email body
    subject = f"⚠️ Chapter Validation Failed: {book_name} (Book ID: {book_id})"

    body_html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .alert {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px; }}
            .details {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
            .details dt {{ font-weight: bold; margin-top: 10px; }}
            .details dd {{ margin-left: 0; margin-bottom: 10px; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🚨 Chapter Validation Alert</h2>

            <div class="alert">
                <strong>Attention Required:</strong> Chapter validation has failed multiple times for this book.
                Automatic resync attempts have been exhausted.
            </div>

            <div class="details">
                <dl>
                    <dt>📚 Book Name:</dt>
                    <dd>{book_name}</dd>

                    <dt>🔢 Book ID:</dt>
                    <dd>{book_id}</dd>

                    <dt>❌ Validation Failure Reason:</dt>
                    <dd>{reason}</dd>

                    <dt>🔄 Retry Attempts:</dt>
                    <dd>{retries} (max retries reached)</dd>

                    <dt>📖 Expected Chapter Count:</dt>
                    <dd>{last_chapter_number}</dd>

                    <dt>📊 Actual Chapter Count:</dt>
                    <dd>{actual_chapter_count}</dd>

                    <dt>⚠️ Discrepancy:</dt>
                    <dd>{abs(last_chapter_number - actual_chapter_count)} chapters</dd>
                </dl>
            </div>

            <h3>Recommended Actions:</h3>
            <ol>
                <li>Check the source website for data availability</li>
                <li>Review backend logs for parsing errors</li>
                <li>Manually trigger resync via admin panel:
                    <code>/admin/jobs/force-resync/{book_id}</code>
                </li>
                <li>If issue persists, check parser logic for edge cases</li>
            </ol>

            <div class="footer">
                <p>This is an automated alert from 看小說 monitoring system.</p>
                <p>Timestamp: {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email
    result = email_sender.email_sender.send_email(
        to_email=to_email,
        subject=subject,
        body=body_html,
        is_html=True,
    )

    if result['status'] == 'error':
        raise HTTPException(status_code=500, detail=f"Failed to send alert email: {result['message']}")

    return {
        "status": "success",
        "message": f"Alert email sent to {to_email}",
        "email_result": result,
    }


@api_router.get("/by-url/chapters", response_model=List[ChapterRef])
def chapters_by_url(book_url: str = Query(...)):
    """
    Fetch chapters by raw book URL (root or page-1).
    """
    try:
        # normalize: if URL ends with '/', use page-1; else use given
        if re.search(r"/\d+/$", book_url):
            url = book_url.rstrip("/") + "/page-1.html"
        else:
            url = book_url
        html_content = fetch_html(url)
        chaps = fetch_chapters_from_liebiao(html_content, url, canonical_base(), start_index=1)
        return [
            ChapterRef(number=ch["number"], title=ch["title"], url=ch["url"])
            for ch in chaps
        ]
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/by-url/content", response_model=ChapterContent)
def content_by_url(chapter_url: str = Query(...)):
    """
    Fetch chapter content directly by its URL.
    Extracts chapter title and number from the HTML content (supports Chinese numerals).
    """
    try:
        chapter_html = fetch_html(chapter_url)
        text = extract_text_by_id(chapter_html, "nr1")

        # Extract book_id from URL
        m_id = re.search(r"/(\d+)/", chapter_url)
        book_id = m_id.group(1) if m_id else None

        # Extract chapter title from HTML
        title = extract_chapter_title(chapter_html)

        # Extract chapter number from title (supports both Arabic and Chinese numerals)
        chapter_num = chapter_title_to_number(title) if title else None

        return ChapterContent(
            book_id=book_id,
            chapter_num=chapter_num,
            title=title,
            url=chapter_url,
            text=text,
        )
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------
# SPA Serving Routes
# -----------------------
# @api_router.get("/")
# async def serve_spa_root():
#     """Serve Vue SPA at root path."""
#     if spa_index_html and os.path.exists(spa_index_html):
#         return FileResponse(spa_index_html)
#     return {"message": "Vue SPA not found. Build the frontend first with 'npm run build'"}


# @api_router.get("/{full_path:path}")
# async def serve_spa_catch_all(full_path: str):
#     """
#     Catch-all route for Vue Router client-side routing.
#     Serves index.html for any non-API routes to enable SPA navigation.

#     API routes are under /xsw/api/* (handled by root_path)
#     Static assets are under /spa/* (handled by StaticFiles mount)
#     All other routes serve the Vue SPA index.html
#     """
#     # Don't intercept API routes (with root_path /xsw/api)
#     if full_path.startswith("xsw/api/"):
#         raise HTTPException(status_code=404, detail="API endpoint not found")

#     # Serve index.html for all SPA routes
#     if spa_index_html and os.path.exists(spa_index_html):
#         return FileResponse(spa_index_html)

#     raise HTTPException(status_code=404, detail="Vue SPA not built. Run 'npm run build' first.")

# -----------------------
# Include API Router
# -----------------------
# IMPORTANT: This must be done AFTER all route definitions above
app.include_router(api_router, prefix="/xsw/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
