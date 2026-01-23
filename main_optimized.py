# main_optimized.py
"""
Optimized FastAPI backend with SQLite database-first caching.
Strategy: Check DB → Fetch from web → Store to DB
"""
import re
from typing import List, Optional
from contextlib import asynccontextmanager
from db_models import init_database
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
import background_jobs as bg_jobs
from background_jobs import init_job_manager
import midnight_sync as midnight
from midnight_sync import init_midnight_scheduler
import periodic_sync as periodic
from periodic_sync import init_periodic_scheduler
import email_sender
from email_sender import init_email_sender

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------
# Configuration
# -----------------------
BASE_URL = os.getenv("BASE_URL", "https://m.xsw.tw")
WWW_BASE = os.getenv("WWW_BASE", "https://www.xsw.tw")
DEFAULT_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))
DB_PATH = os.getenv("DB_PATH", "xsw_cache.db")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "900"))

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
# Background Job Callbacks
# -----------------------
def _bg_fetch_book_info(book_id: str):
    """Background job callback to fetch and cache book info."""
    try:
        # Check if already cached
        cached_info = cache_mgr.cache_manager.get_book_info(book_id)
        if cached_info:
            print(f"[BG] Book {book_id} info already cached")
            return

        # Fetch from web
        url = resolve_book_home(book_id)
        html_content = fetch_html(url)
        info = parse_book_info(html_content, BASE_URL)

        if info:
            info["book_id"] = book_id
            info["source_url"] = url
            cache_mgr.cache_manager.store_book_info(book_id, info)
            print(f"[BG] Cached book info for {book_id}")
    except Exception as e:
        print(f"[BG] Failed to fetch book info for {book_id}: {e}")
        raise


def _bg_fetch_chapters(book_id: str):
    """Background job callback to fetch and cache all chapters."""
    try:
        # Check if already cached
        cached_chapters = cache_mgr.cache_manager.get_chapter_list(book_id)
        if cached_chapters and len(cached_chapters) > 0:
            print(f"[BG] Book {book_id} already has {len(cached_chapters)} chapters cached")
            return

        # Fetch from web
        url = resolve_book_home(book_id)
        html_content = fetch_html(url)
        items = fetch_chapters_from_liebiao(html_content, page_url=url, canonical_base=canonical_base())

        if items:
            # Store chapter references (metadata only, not content)
            cache_mgr.cache_manager.store_chapter_refs(book_id, items)
            print(f"[BG] Cached {len(items)} chapter references for {book_id}")
    except Exception as e:
        print(f"[BG] Failed to fetch chapters for {book_id}: {e}")
        raise


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
    db_mgr = init_database(f"sqlite:///{DB_PATH}")
    init_cache_manager(ttl_seconds=CACHE_TTL)

    # Initialize background job manager
    num_workers = int(os.getenv("BG_JOB_WORKERS", "2"))
    rate_limit = float(os.getenv("BG_JOB_RATE_LIMIT", "2.0"))
    init_job_manager(num_workers=num_workers, rate_limit_seconds=rate_limit)

    # Set up job callbacks
    bg_jobs.job_manager.fetch_book_info_callback = _bg_fetch_book_info
    bg_jobs.job_manager.fetch_chapters_callback = _bg_fetch_chapters

    # Start background workers
    bg_jobs.job_manager.start()

    # Initialize midnight sync scheduler
    sync_hour = int(os.getenv("MIDNIGHT_SYNC_HOUR", "0"))  # Default: midnight
    sync_minute = int(os.getenv("MIDNIGHT_SYNC_MINUTE", "0"))
    slow_rate = float(os.getenv("MIDNIGHT_SYNC_RATE_LIMIT", "5.0"))  # Default: 5s between books
    init_midnight_scheduler(
        db_session_factory=db_mgr.get_session,
        job_manager=bg_jobs.job_manager,
        sync_hour=sync_hour,
        sync_minute=sync_minute,
        slow_rate_limit=slow_rate,
    )

    # Start midnight scheduler
    midnight.midnight_scheduler.start()

    # Initialize periodic sync scheduler (runs every 6 hours)
    periodic_interval = int(os.getenv("PERIODIC_SYNC_HOURS", "6"))  # Default: 6 hours
    periodic_priority = int(os.getenv("PERIODIC_SYNC_PRIORITY", "3"))  # Default: priority 3
    init_periodic_scheduler(
        db_session_factory=db_mgr.get_session,
        job_manager=bg_jobs.job_manager,
        interval_hours=periodic_interval,
        sync_priority=periodic_priority,
    )

    # Start periodic scheduler
    periodic.periodic_scheduler.start()

    print(f"[App] Database, cache, {num_workers} background workers, midnight scheduler, and periodic sync (every {periodic_interval}h) initialized")

    yield  # Application runs here

    # Shutdown: Stop background workers and cleanup
    print("[App] Shutting down background workers and schedulers...")
    if periodic.periodic_scheduler:
        periodic.periodic_scheduler.stop()
    if midnight.midnight_scheduler:
        midnight.midnight_scheduler.stop()
    if bg_jobs.job_manager:
        bg_jobs.job_manager.stop()
    print("[App] Shutdown complete")

app = FastAPI(
    title="看小說 API (Optimized)",
    version="2.0.0",
    root_path="/xsw/api",
    description="Optimized API with SQLite database-first caching",
    lifespan=lifespan
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
# Routes
# -----------------------
@app.get("/health")
def health():
    """Health check with cache and job stats."""
    cache_stats = cache_mgr.cache_manager.get_stats() if cache_mgr.cache_manager else {}
    job_stats = bg_jobs.job_manager.get_stats() if bg_jobs.job_manager else {}
    return {
        "status": "ok",
        "base_url": BASE_URL,
        "db_path": DB_PATH,
        "cache_stats": cache_stats,
        "job_stats": job_stats,
    }


@app.get("/categories", response_model=List[Category])
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


@app.get("/categories/{cat_id}/books", response_model=List[BookSummary])
def list_books_in_category(
    cat_id: int,
    page: int = Query(1, ge=1),
    bg_sync: bool = Query(True, description="Trigger background sync for books")
):
    """
    List books in category (not cached, real-time).

    Optionally triggers background jobs to pre-cache book info and chapters.
    Set bg_sync=false to disable background syncing.
    """
    try:
        url = f"{BASE_URL}/fenlei{cat_id}_{page}.html"
        html_content = fetch_html(url)
        books = parse_books(html_content, BASE_URL)

        book_summaries = [
            BookSummary(**b, book_id=extract_book_id_from_url(b["bookurl"]))
            for b in books
        ]

        # Trigger background sync jobs for all books on this page
        if bg_sync and bg_jobs.job_manager:
            book_ids = [bs.book_id for bs in book_summaries if bs.book_id]
            queued = bg_jobs.job_manager.enqueue_batch(book_ids, priority=0)
            print(f"[API] Category {cat_id} page {page}: Queued {queued}/{len(book_ids)} books for background sync")

        return book_summaries
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
        # Track book access for midnight sync
        if midnight.midnight_scheduler:
            midnight.midnight_scheduler.track_book_access(book_id)

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


@app.get("/books/{book_id}/chapters", response_model=List[ChapterRef])
def get_book_chapters(
    book_id: str,
    page: int = Query(1, ge=1),
    nocache: bool = Query(False),
    www: bool = Query(False),
    all: bool = Query(False)
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
                home_url = resolve_book_home(book_id)
                html_content = fetch_html(home_url)
                items = fetch_chapters_from_liebiao(html_content, home_url, canonical_base())
            else:
                # Fetch from pagination pages (all chapters)
                items = fetch_all_chapters_from_pagination(book_id)

            if not items:
                raise HTTPException(status_code=404, detail="No chapters found")

            # Store to DB
            cache_mgr.cache_manager.store_chapter_refs(book_id, items)

            # Convert to ChapterRef list
            all_chapters = [
                ChapterRef(number=item["number"], title=item["title"], url=item["url"])
                for item in items
                if item.get("number") is not None
            ]

            # Sync book info with actual last chapter from fetched chapters
            if all_chapters:
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
        if all:
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

    # Collect all chapters from all pages
    all_items = []
    for page_num in range(1, total_pages + 1):
        page_url = f"{base}/{book_id}/page-{page_num}.html"
        html_content = fetch_html(page_url)
        items = fetch_chapters_from_liebiao(html_content, page_url, base)
        all_items.extend(items)
        print(f"[API] Page {page_num}/{total_pages}: found {len(items)} chapters")

    return all_items


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
            items = fetch_chapters_from_liebiao(home_html, home_url, canonical_base())

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


@app.get("/search")
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
# Admin Endpoints
# -----------------------
@app.get("/admin/jobs/stats")
def get_job_stats():
    """Get background job statistics."""
    if not bg_jobs.job_manager:
        return {"error": "Background job manager not initialized"}
    return bg_jobs.job_manager.get_stats()


@app.post("/admin/jobs/sync/{book_id}")
def trigger_book_sync(book_id: str, priority: int = Query(10, description="Job priority (higher = first)")):
    """Manually trigger background sync for a specific book."""
    if not bg_jobs.job_manager:
        raise HTTPException(status_code=503, detail="Background job manager not available")

    queued = bg_jobs.job_manager.enqueue_sync(book_id, priority=priority)
    if queued:
        return {"status": "queued", "book_id": book_id, "priority": priority}
    else:
        return {"status": "already_queued_or_syncing", "book_id": book_id}


@app.post("/admin/jobs/force-resync/{book_id}")
def force_resync_book(
    book_id: str,
    priority: int = Query(10, description="Job priority (higher = first)"),
    clear_cache: bool = Query(True, description="Clear book cache before resync"),
):
    """
    Force resync a book, bypassing recent completion checks.
    Useful for resyncing books that may have missing chapters due to:
    - Previous parsing errors (e.g., Chinese numeral support was missing)
    - Incomplete sync
    - Data corruption

    This will:
    1. Optionally clear the book's cache
    2. Remove the book from recently completed list
    3. Queue the book for immediate resync
    """
    if not bg_jobs.job_manager:
        raise HTTPException(status_code=503, detail="Background job manager not available")

    # Clear cache if requested
    if clear_cache and cache_mgr.cache_manager:
        cache_mgr.cache_manager.invalidate_book(book_id)

    # Force resync
    queued = bg_jobs.job_manager.force_resync(book_id, priority=priority)
    if queued:
        return {
            "status": "queued",
            "book_id": book_id,
            "priority": priority,
            "cache_cleared": clear_cache,
            "message": "Book queued for forced resync",
        }
    else:
        return {
            "status": "already_syncing",
            "book_id": book_id,
            "message": "Book is currently being synced, cannot force resync",
        }


@app.post("/admin/jobs/clear_history")
def clear_job_history():
    """Clear completed and failed job history."""
    if not bg_jobs.job_manager:
        raise HTTPException(status_code=503, detail="Background job manager not available")

    bg_jobs.job_manager.clear_history()
    return {"status": "cleared", "message": "Job history cleared"}


@app.post("/admin/init-sync")
def admin_init_sync(
    categories_limit: int = Query(7, ge=1, le=20, description="Number of categories to scan"),
    pages_per_category: int = Query(10, ge=1, le=50, description="Pages to scan per category"),
):
    """
    Initialize full sync: Drop all data, scan categories, and queue all books.

    This will:
    1. Clear all database tables (books, chapters, categories, sync queue)
    2. Fetch categories from homepage
    3. Scan books from first N categories (default 7)
    4. Queue all discovered books for background sync

    WARNING: This is a destructive operation that will delete all existing data!
    """
    import db_models
    from db_models import Book, Chapter, Category, PendingSyncQueue

    if not bg_jobs.job_manager:
        raise HTTPException(status_code=503, detail="Background job manager not available")

    if not db_models.db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    session = db_models.db_manager.get_session()
    try:
        # Step 1: Clear all data

        print("[INIT_SYNC] Clearing all data...")
        deleted_chapters = session.query(Chapter).delete()
        deleted_books = session.query(Book).delete()
        deleted_categories = session.query(Category).delete()
        deleted_queue = session.query(PendingSyncQueue).delete()
        session.commit()
        print(f"[INIT_SYNC] Deleted: {deleted_books} books, {deleted_chapters} chapters, {deleted_categories} categories, {deleted_queue} queue items")

        # Clear memory cache
        if cache_mgr.cache_manager:
            cache_mgr.cache_manager.clear_memory_cache()

        # Clear job manager state
        bg_jobs.job_manager.clear_all()

        # Step 2: Fetch categories
        print("[INIT_SYNC] Fetching categories...")
        home_url = BASE_URL + "/"
        html_content = fetch_html(home_url)
        cats = find_categories_from_nav(html_content, BASE_URL)
        print(f"[INIT_SYNC] Found {len(cats)} categories")

        # Limit categories
        cats_to_scan = cats[:categories_limit]
        print(f"[INIT_SYNC] Will scan {len(cats_to_scan)} categories")

        # Step 3: Scan books from categories
        total_books_found = 0
        book_ids_to_queue = set()

        for cat in cats_to_scan:
            cat_id = cat["id"]
            cat_name = cat["name"]
            print(f"[INIT_SYNC] Scanning category {cat_id} ({cat_name})...")

            for page in range(1, pages_per_category + 1):
                try:
                    url = f"{BASE_URL}/fenlei{cat_id}_{page}.html"
                    html = fetch_html(url)
                    books = parse_books(html, BASE_URL)

                    for book in books:
                        book_id = extract_book_id_from_url(book["bookurl"])
                        if book_id:
                            book_ids_to_queue.add(book_id)

                    print(f"[INIT_SYNC]   Page {page}: Found {len(books)} books")
                    total_books_found += len(books)
                except Exception as e:
                    print(f"[INIT_SYNC]   Page {page}: Error - {e}")
                    continue

        # Step 4: Queue all books
        print(f"[INIT_SYNC] Queuing {len(book_ids_to_queue)} unique books...")
        queued = bg_jobs.job_manager.enqueue_batch(list(book_ids_to_queue), priority=5)

        return {
            "status": "initialized",
            "deleted": {
                "books": deleted_books,
                "chapters": deleted_chapters,
                "categories": deleted_categories,
                "queue_items": deleted_queue,
            },
            "scanned": {
                "categories": len(cats_to_scan),
                "pages_per_category": pages_per_category,
                "total_books_found": total_books_found,
                "unique_books": len(book_ids_to_queue),
            },
            "queued": queued,
            "message": f"Initialized sync: queued {queued} books from {len(cats_to_scan)} categories"
        }
    except Exception as e:
        session.rollback()
        print(f"[INIT_SYNC] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/admin/cache/clear")
def clear_memory_cache():
    """Clear in-memory cache (DB remains intact)."""
    cache_mgr.cache_manager.clear_memory_cache()
    return {"status": "cleared", "message": "Memory cache cleared"}


@app.post("/admin/cache/invalidate/{book_id}")
def invalidate_book_cache(book_id: str):
    """Invalidate cache for a specific book."""
    cache_mgr.cache_manager.invalidate_book(book_id)
    return {"status": "invalidated", "book_id": book_id}


@app.get("/admin/stats")
def get_cache_stats():
    """Get detailed cache statistics."""
    return cache_mgr.cache_manager.get_stats()


@app.get("/admin/midnight-sync/stats")
def get_midnight_sync_stats():
    """Get midnight sync queue statistics."""
    if not midnight.midnight_scheduler:
        return {"error": "Midnight sync scheduler not initialized"}
    return midnight.midnight_scheduler.get_queue_stats()


@app.post("/admin/midnight-sync/clear-completed")
def clear_midnight_sync_completed():
    """Clear completed and failed entries from midnight sync queue."""
    if not midnight.midnight_scheduler:
        raise HTTPException(status_code=503, detail="Midnight sync scheduler not available")

    cleared = midnight.midnight_scheduler.clear_completed()
    return {"status": "cleared", "removed_count": cleared, "message": f"Cleared {cleared} completed/failed entries"}


@app.post("/admin/midnight-sync/trigger")
def trigger_midnight_sync_now():
    """Manually trigger the midnight sync process immediately."""
    if not midnight.midnight_scheduler:
        raise HTTPException(status_code=503, detail="Midnight sync scheduler not available")

    # Run sync in a background thread to avoid blocking the request
    import threading
    thread = threading.Thread(
        target=midnight.midnight_scheduler._run_midnight_sync,
        name="manual-midnight-sync",
        daemon=True,
    )
    thread.start()

    return {
        "status": "triggered",
        "message": "Midnight sync started in background",
    }


@app.post("/admin/midnight-sync/enqueue-unfinished")
def enqueue_unfinished_books():
    """
    Manually enqueue all unfinished books (status != '已完成') to the midnight sync queue.

    This endpoint finds all books in the database that are not marked as completed
    and adds them to the pending sync queue with priority 1.

    Returns:
        Number of books added to the queue
    """
    if not midnight.midnight_scheduler:
        raise HTTPException(status_code=503, detail="Midnight sync scheduler not available")

    added_count = midnight.midnight_scheduler.enqueue_unfinished_books()

    return {
        "status": "success",
        "added_count": added_count,
        "message": f"Added {added_count} unfinished books to sync queue",
    }


# ============================================
# Periodic Sync Endpoints
# ============================================


@app.get("/admin/periodic-sync/stats")
def get_periodic_sync_stats():
    """Get periodic sync scheduler statistics."""
    if not periodic.periodic_scheduler:
        return {"error": "Periodic sync scheduler not initialized"}
    return periodic.periodic_scheduler.get_stats()


@app.post("/admin/periodic-sync/trigger")
def trigger_periodic_sync_now():
    """Manually trigger the periodic sync process immediately."""
    if not periodic.periodic_scheduler:
        raise HTTPException(status_code=503, detail="Periodic sync scheduler not available")

    try:
        periodic.periodic_scheduler.trigger_sync()
        return {
            "status": "triggered",
            "message": "Periodic sync completed successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger periodic sync: {str(e)}")


# ============================================
# SMTP & Email Endpoints
# ============================================


@app.get("/admin/smtp/settings")
def get_smtp_settings():
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


@app.post("/admin/smtp/settings")
def save_smtp_settings(
    smtp_host: str = Query(...),
    smtp_port: int = Query(...),
    smtp_user: str = Query(...),
    smtp_password: str = Query(...),
    use_tls: bool = Query(True),
    use_ssl: bool = Query(False),
    from_email: str = Query(None),
    from_name: str = Query("看小說 Admin"),
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


@app.post("/admin/smtp/test")
def test_smtp_connection():
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


@app.post("/admin/email/send")
def send_email(
    to_email: str = Query(...),
    subject: str = Query(...),
    body: str = Query(...),
    is_html: bool = Query(False),
    cc: str = Query(None),
    bcc: str = Query(None),
    attachments: str = Query(None),
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


@app.post("/admin/upload")
async def upload_file(file: UploadFile = File(...)):
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


@app.get("/by-url/chapters", response_model=List[ChapterRef])
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
        chaps = fetch_chapters_from_liebiao(html_content, BASE_URL)
        return [
            ChapterRef(number=k, title=v["title"], url=v["url"])
            for k, v in sorted(chaps.items())
        ]
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/by-url/content", response_model=ChapterContent)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
