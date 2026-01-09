# main.py
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from bs4 import BeautifulSoup
import html as html_unescape
import re
import requests
from urllib.parse import urljoin
import os

import time
import threading

import logging

# Configure basic logging (put this near the top of main.py)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("book-scraper")


# -----------------------
# Configuration & Session
# -----------------------
BASE_URL = os.getenv("BASE_URL")
DEFAULT_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))

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
# Simple TTL cache
# -----------------------
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "900"))  # 15 minutes
CACHE_MAX_ITEMS = int(os.getenv("CACHE_MAX_ITEMS", "200"))


class TTLCache:
    """
    Simple thread-safe TTL cache with oldest-evict policy when full.
    Keys are hashable; values are any Python object (Pydantic models OK).
    """

    def __init__(self, ttl_seconds: int, max_items: int):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._store: Dict[Any, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            ts, value = entry
            if now - ts > self.ttl:
                # expired
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        now = time.time()
        with self._lock:
            # Evict if full
            if len(self._store) >= self.max_items:
                # remove oldest by timestamp
                oldest_key = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest_key, None)
            self._store[key] = (now, value)

    def invalidate(self, key: Any) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Instantiate caches
chapters_page_cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS, max_items=CACHE_MAX_ITEMS)
chapters_all_cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS, max_items=CACHE_MAX_ITEMS)
chapter_url_cache = TTLCache(
    ttl_seconds=CACHE_TTL_SECONDS, max_items=2000
)  # mapping cache {(book_id, num) -> url}


# -------------
# Fetch helpers
# -------------
def fetch_html(url: str) -> str:
    """
    Fetch raw HTML content from URL with robust encoding handling.
    """
    resp = session.get(url, timeout=DEFAULT_TIMEOUT, verify=False)
    resp.raise_for_status()
    # Prefer server-provided or detected encoding; default to utf-8
    enc = resp.apparent_encoding or resp.encoding or "utf-8"
    resp.encoding = enc
    return resp.text

    """
    Fetch raw HTML content from a given URL.
    """
    resp = requests.get(url, verify=False)

    enc = resp.apparent_encoding or resp.encoding or "utf-8"
    resp.encoding = enc
    return resp.text


def extract_text_by_id(html_content: str, element_id: str) -> str:
    """
    Extract and normalize text from an element by id.
    Preserves logical breaks, normalizes whitespace.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    target = soup.find(id=element_id)
    if not target:
        return ""
    text_content = html_unescape.unescape(target.get_text(separator="\n"))
    normalized = re.sub(r"\s+", " ", text_content).strip()
    return normalized


def parse_chapters(html_content: str, base_url: str = "") -> Dict[int, Dict[str, str]]:
    """
    Parse <ul class="chapter"> into {chapter_number: {'url': full_url, 'title': title}}
    """
    soup = BeautifulSoup(html_content, "html.parser")
    chapters: Dict[int, Dict[str, str]] = {}
    ul = soup.find("ul", class_="chapter")
    if not ul:
        return chapters

    for a_tag in ul.find_all("a", href=True):
        raw_text = html_unescape.unescape(a_tag.get_text(strip=True))
        href = a_tag["href"]
        match = re.search(r"第(\d+)章", raw_text)
        if match:
            chapter_num = int(match.group(1))
            title = raw_text
            full_url = urljoin(base_url or "", href)
            chapters[chapter_num] = {"url": full_url, "title": title}
    return chapters


def get_page_count(html_content: str) -> int:
    """
    Extract total pages from <div class="page"> e.g., (第1/70頁)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    page_div = soup.find("div", class_="page")
    if not page_div:
        return 0
    text = page_div.get_text(strip=True)
    m = re.search(r"第\d+/(\d+)頁", text)
    return int(m.group(1)) if m else 0


def parse_book_info(html_content: str, base_url: str = "") -> Dict[str, Any]:
    """
    Parse <div class="block_txt2"> for book details.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    block = soup.find("div", class_="block_txt2")
    if not block:
        return {}

    name = block.find("h2").get_text(strip=True) if block.find("h2") else ""

    status_tag = block.find("p", string=lambda t: t and "狀態" in t)
    status = status_tag.get_text(strip=True).replace("狀態：", "") if status_tag else ""

    update_tag = block.find("p", string=lambda t: t and "更新" in t)
    update = update_tag.get_text(strip=True).replace("更新：", "") if update_tag else ""

    author = ""
    book_type = ""
    last_chapter_title = ""
    last_chapter_url = ""
    last_chapter_number: Optional[int] = None

    for p in block.find_all("p"):
        text = p.get_text(strip=True)
        if text.startswith("作者"):
            a_tag = p.find("a")
            author = a_tag.get_text(strip=True) if a_tag else ""
        elif text.startswith("分類"):
            a_tag = p.find("a")
            book_type = a_tag.get_text(strip=True) if a_tag else ""
        elif text.startswith("最新"):
            a_tag = p.find("a")
            if a_tag:
                last_chapter_title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                last_chapter_url = urljoin(base_url or "", href)
                match = re.search(r"第(\d+)章", last_chapter_title)
                if match:
                    last_chapter_number = int(match.group(1))

    return {
        "name": name,
        "author": author,
        "type": book_type,
        "status": status,
        "update": update,
        "last_chapter_title": last_chapter_title,
        "last_chapter_url": last_chapter_url,
        "last_chapter_number": last_chapter_number,
    }


def parse_books(html: str, base_url: str = "") -> List[Dict[str, str]]:
    """
    Parse book list boxes:
    returns [{bookname, author, lastchapter, intro, bookurl}, ...]
    """
    soup = BeautifulSoup(html, "lxml")
    out: List[Dict[str, str]] = []
    for box in soup.select("div.bookbox"):
        name_tag = box.select_one("div.bookinfo h4.bookname i.iTit a")
        bookname = (name_tag.get_text(strip=True) if name_tag else "").strip()
        href = name_tag.get("href", "") if name_tag else ""
        bookurl = urljoin(base_url or "", href)

        author_tag = box.select_one("div.bookinfo div.author")
        author_raw = author_tag.get_text(" ", strip=True) if author_tag else ""
        author = author_raw.replace("作者：", "").replace("作者:", "").strip()

        chapter_tag = box.select_one("div.bookinfo div.update a")
        lastchapter = chapter_tag.get_text(strip=True).strip() if chapter_tag else ""

        intro_tag = box.select_one("div.bookinfo div.intro_line")
        intro_text = intro_tag.get_text(" ", strip=True) if intro_tag else ""
        intro = intro_text.replace("簡介：", "").replace("简介：", "").strip()

        out.append(
            {
                "bookname": bookname,
                "author": author,
                "lastchapter": lastchapter,
                "intro": intro,
                "bookurl": bookurl,
            }
        )
    return out


# ----------------
# Extra utilities
# ----------------
def extract_book_id_from_url(bookurl: str) -> Optional[str]:
    m = re.search(r"https?://[^/]+/(\d+)/", bookurl)
    return m.group(1) if m else None


def resolve_category_page(cat_id: int, page: int) -> str:
    return f"{BASE_URL}/fenlei{cat_id}_{page}.html"


def resolve_book_home(book_id: str) -> str:
    return f"{BASE_URL}/{book_id}/"


def resolve_book_page(book_id: str, page_num: int) -> str:
    return f"{BASE_URL}/{book_id}/page-{page_num}.html"


def find_categories_from_nav(home_html: str):
    """
    Best-effort approach: find anchors linking to 'fenleiX_1.html' in nav/header.
    """
    soup = BeautifulSoup(home_html, "html.parser")
    cats: List[Dict[str, str]] = []
    anchors = soup.find_all("a", href=True)
    for a in anchors:
        href = a["href"]
        if re.search(r"fenlei(\d+)_1\.html", href):
            m = re.search(r"fenlei(\d+)_1\.html", href)
            cat_id = m.group(1) if m else ""
            cats.append(
                {
                    "id": cat_id,
                    "name": a.get_text(),
                    "url": urljoin(BASE_URL + "/", href),
                }
            )
    # Deduplicate by id
    seen = set()
    uniq = []
    for c in cats:
        if c["id"] not in seen:
            uniq.append(c)
            seen.add(c["id"])
    return uniq


# ------------
# Data models
# ------------
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


class BookInfo(BaseModel):
    name: str
    author: str
    type: str
    status: str
    update: str
    last_chapter_title: str
    last_chapter_url: str
    last_chapter_number: Optional[int] = None
    book_id: Optional[str] = None


class ChapterRef(BaseModel):
    number: int
    title: str
    url: str


class ChapterContent(BaseModel):
    book_id: Optional[str] = None
    chapter_num: Optional[int] = None
    title: Optional[str] = None
    url: str
    text: str


# -----
# App
# -----
app = FastAPI(title="Book Scraper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Path to your SPA build folder
spa_dir = "/app/dist/spa"

# Mount the SPA folder at /spa
app.mount("/spa", StaticFiles(directory=spa_dir), name="spa")


# -------
# Routes
# -------
@app.get("/health")
def health():
    return {"status": "ok", "base_url": BASE_URL}


@app.get("/categories", response_model=List[Category])
def get_categories():
    """
    Scrape categories by scanning homepage for fenlei{cat_id}_1.html anchors.
    """
    home_url = BASE_URL + "/"
    try:
        html_content = fetch_html(home_url)
        cats = find_categories_from_nav(html_content)
        return [Category(**c) for c in cats]
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/categories/{cat_id}/books", response_model=List[BookSummary])
def list_books_in_category(cat_id: int, page: int = Query(1, ge=1)):
    """
    Return books under a category page: /fenlei{cat_id}_{page}.html
    """
    url = resolve_category_page(cat_id, page)
    try:
        html_content = fetch_html(url)
        books = parse_books(html_content, BASE_URL)
        # attach book_id if detectable
        enriched = []
        for b in books:
            enriched.append(
                BookSummary(**b, book_id=extract_book_id_from_url(b["bookurl"]))
            )
        return enriched
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/books/{book_id}", response_model=BookInfo)
def get_book_info(book_id: str):
    """
    Book metadata from /{book_id}/
    """
    url = resolve_book_home(book_id)
    try:
        html_content = fetch_html(url)
        info = parse_book_info(html_content, BASE_URL)
        if not info:
            raise HTTPException(status_code=404, detail="Book info not found")
        return BookInfo(**info, book_id=book_id)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/books/{book_id}/chapters", response_model=List[ChapterRef])
def get_book_chapters(
    book_id: str,
    page: int = Query(1, ge=1),
    all: bool = Query(False),
    max_pages: int = Query(0, ge=0),
    nocache: bool = Query(False, description="Set true to bypass caches"),
):
    """
    Get chapter links.
    - If all=false: returns chapters from the requested page only (cached by (book_id, page)).
    - If all=true: scans multiple pages.
        * If page is provided and max_pages=1 -> scans only that page.
        * If page is provided and max_pages=0 -> scans from 'page' to 'effective_pages'.
        * If page is 1 and max_pages=0 -> scans from 1 to 'effective_pages' (original behavior).
    Caches aggregate results by (book_id, 'ALL', start_page, effective_pages).
    Also
    """
    try:
        if not all:
            cache_key = (book_id, page)
            if not nocache:
                cached = chapters_page_cache.get(cache_key)
                if cached is not None:
                    logger.debug(f"[CACHE HIT] chapters_page_cache {cache_key}")
                    return cached

            url = resolve_book_page(book_id, page)
            html_content = fetch_html(url)
            chaps = parse_chapters(html_content, BASE_URL)

            # Warm mapping cache for this page
            for num, ref in chaps.items():
                chapter_url_cache.set((book_id, num), ref["url"])

            result = [
                ChapterRef(number=k, title=v["title"], url=v["url"])
                for k, v in sorted(chaps.items())
            ]
            chapters_page_cache.set(cache_key, result)

            return result

        # all pages mode
        first_url = resolve_book_page(book_id, 1)

        logger.debug(f"[FETCH] probe first page for total_pages: {first_url}")

        first_html = fetch_html(first_url)
        total_pages = get_page_count(first_html)

        effective_pages = total_pages if total_pages > 0 else 1

        # Compute scanning window
        # - If max_pages == 1, scan only 'page'
        # - If max_pages == 0, scan 'page'..effective_pages
        # - If max_pages > 1, scan 'page'..min(page + max_pages - 1, effective_pages)
        start_page = max(page, 1)

        if max_pages == 1:
            end_page = start_page
        elif max_pages == 0:
            end_page = effective_pages
        else:
            end_page = min(start_page + max_pages - 1, effective_pages)

        # Cache key includes the scanning window

        cache_key = (book_id, "ALL", start_page, end_page)
        if not nocache:
            cached = chapters_all_cache.get(cache_key)
            if cached is not None:

                logger.debug(f"[CACHE HIT] chapters_all_cache {cache_key}")

                return cached

        merged: Dict[int, Dict[str, str]] = {}
        for p in range(1, effective_pages + 1):
            page_url = resolve_book_page(book_id, p)
            html_content = fetch_html(page_url)
            chaps = parse_chapters(html_content, base_url=page_url)
            merged.update(chaps)
            # Warm mapping cache
            for num, ref in chaps.items():
                chapter_url_cache.set((book_id, num), ref["url"])

        result = [
            ChapterRef(number=k, title=v["title"], url=v["url"])
            for k, v in sorted(merged.items())
        ]
        chapters_all_cache.set(cache_key, result)
        return result

        # if no pagination detected, try root page as fallback
        # pages_to_scan = total_pages if total_pages > 0 else 1
        # merged: Dict[int, Dict[str, str]] = {}
        # for p in range(1, pages_to_scan + 1):
        #     page_url = resolve_book_page(book_id, p)
        #     html_content = fetch_html(page_url)
        #     chaps = parse_chapters(html_content, BASE_URL)
        #     merged.update(chaps)

        # return [ChapterRef(number=k, title=v["title"], url=v["url"]) for k, v in sorted(merged.items())]
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/books/{book_id}/chapters/{chapter_num}", response_model=ChapterContent)
def get_chapter_content(
    book_id: str,
    chapter_num: int,
    nocache: bool = Query(False, description="Set true to bypass caches"),
):
    """
    Resolve chapter URL using the mapping cache or by scanning chapter list pages,
    then extract text (id 'nr1' with fallbacks).
    """

    try:
        # 1) Try mapping cache first (unless bypassed)
        target_url: Optional[str] = None
        target_title: Optional[str] = None

        if not nocache:
            cached_url = chapter_url_cache.get((book_id, chapter_num))
            if cached_url:
                target_url = cached_url

        # 2) If not cached, scan pages to locate and warm the cache
        if not target_url:
            first_url = resolve_book_page(book_id, 1)
            first_html = fetch_html(first_url)
            total_pages = get_page_count(first_html)
            pages_to_scan = total_pages if total_pages > 0 else 1

            for p in range(1, pages_to_scan + 1):
                page_url = resolve_book_page(book_id, p)
                html_content = fetch_html(page_url)
                chaps = parse_chapters(html_content, base_url=page_url)
                # Warm mapping cache for all chapters on this page
                for num, ref in chaps.items():
                    chapter_url_cache.set((book_id, num), ref["url"])
                if chapter_num in chaps:
                    target_url = chaps[chapter_num]["url"]
                    target_title = chaps[chapter_num]["title"]
                    break

        if not target_url:
            raise HTTPException(
                status_code=404, detail=f"Chapter {chapter_num} not found"
            )

        # 3) Fetch content and apply robust id fallbacks
        chapter_html = fetch_html(target_url)
        text = (
            extract_text_by_id(chapter_html, "nr1")
            or extract_text_by_id(chapter_html, "nr")
            or extract_text_by_id(chapter_html, "content")
        )

        if not text:
            raise HTTPException(
                status_code=404, detail=f"No content found in {target_url}"
            )

        return ChapterContent(
            book_id=book_id,
            chapter_num=chapter_num,
            title=target_title,
            url=target_url,
            text=text,
        )

        # # Find chapter URL by scanning pages
        # first_url = resolve_book_page(book_id, 1)
        # first_html = fetch_html(first_url)
        # total_pages = get_page_count(first_html)
        # pages_to_scan = total_pages if total_pages > 0 else 1

        # target_url = None
        # target_title = None
        # for p in range(1, pages_to_scan + 1):
        #     page_url = resolve_book_page(book_id, p)
        #     html_content = fetch_html(page_url)
        #     chaps = parse_chapters(html_content, BASE_URL)
        #     if chapter_num in chaps:
        #         target_url = chaps[chapter_num]["url"]
        #         target_title = chaps[chapter_num]["title"]
        #         break

        # if not target_url:
        #     raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")

        # chapter_html = fetch_html(target_url)
        # text = extract_text_by_id(chapter_html, "nr1")
        # return ChapterContent(book_id=book_id, chapter_num=chapter_num, title=target_title, url=target_url, text=text)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------
# Optional admin ops
# -------------------
@app.post("/admin/cache/chapters/page/clear")
def clear_chapters_page_cache():
    chapters_page_cache.clear()
    return {"status": "cleared"}


@app.post("/admin/cache/chapters/all/clear")
def clear_chapters_all_cache():
    chapters_all_cache.clear()
    return {"status": "cleared"}


@app.post("/admin/cache/chapters/mapping/clear")
def clear_chapter_url_mapping_cache():
    chapter_url_cache.clear()
    return {"status": "cleared"}


# -------------------
# Related convenience
# -------------------
@app.get("/search", response_model=List[BookSummary])
def search_books(q: str = Query(..., min_length=1), page: int = Query(1, ge=1)):
    """
    Very simple heuristic search over a category page (adjust cat_id as needed).
    For production, wire a proper site search if available.
    """
    # Default to category 2 (example) – adjust per your site structure.
    cat_id = 2
    url = resolve_category_page(cat_id, page)
    try:
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
        chaps = parse_chapters(html_content, BASE_URL)
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
    """
    try:
        chapter_html = fetch_html(chapter_url)
        text = extract_text_by_id(chapter_html, "nr1")
        # Try to guess book_id & chapter_num
        m_id = re.search(r"/(\d+)/", chapter_url)
        m_num = re.search(r"第(\d+)章", chapter_url)  # may not exist in URL
        book_id = m_id.group(1) if m_id else None
        chapter_num = int(m_num.group(1)) if m_num else None
        return ChapterContent(
            book_id=book_id,
            chapter_num=chapter_num,
            title=None,
            url=chapter_url,
            text=text,
        )
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
