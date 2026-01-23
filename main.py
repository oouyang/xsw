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
from urllib.parse import urljoin, urlparse, urlunparse
import os
import urllib3
import time
import threading
import logging
from math import ceil

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure basic logging (put this near the top of main.py)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("book-scraper")


# -----------------------
# Configuration & Session
# -----------------------
BASE_URL = os.getenv("BASE_URL")
DEFAULT_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))
CHAPTERS_PAGE_SIZE = int(os.getenv("CHAPTERS_PAGE_SIZE", "20"))  # server-side pagination size

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
# Domain helpers (m vs www)
# -----------------------
def canonical_base() -> str:
    """Return the canonical scheme+host chosen by BASE_URL."""
    p = urlparse(BASE_URL)
    # normalize to scheme://host (no trailing slash)
    return f"{p.scheme}://{p.netloc}"

def is_mobile_site() -> bool:
    return "m.xsw.tw" in canonical_base()

def resolve_book_home(book_id: str) -> str:
    """
    Book home URL depends on domain:
      - www.xsw.tw → /book/{id}/
      - m.xsw.tw   → /{id}/
    """
    base = canonical_base()
    if is_mobile_site():
        return f"{base}/{book_id}/"
    else:
        return f"{base}/book/{book_id}/"

def rewrite_to_canonical(url: str) -> str:
    """Rewrite any absolute URL to the canonical scheme+host, preserving path/query."""
    target = urlparse(url)
    base = urlparse(canonical_base())
    return urlunparse((base.scheme, base.netloc, target.path, target.params, target.query, target.fragment))

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
    # resp = requests.get(url, verify=False)
    resp.raise_for_status()
    # Prefer server-provided or detected encoding; default to utf-8
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


def extract_chapter_title(html_content: str) -> Optional[str]:
    """
    Extract chapter title from a chapter page.
    Tries multiple strategies to find the title.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Strategy 1: Look for h1 with chapter pattern
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
        if re.search(r"第.+章", title):
            return title

    # Strategy 2: Look for div/h2 with class containing "title" or "chapter"
    for tag in soup.find_all(["h1", "h2", "h3", "div"], class_=re.compile(r"(title|chapter|tit)", re.I)):
        title = tag.get_text(strip=True)
        if re.search(r"第.+章", title):
            return title

    # Strategy 3: Look in page title
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Extract just the chapter part if it exists
        match = re.search(r"(第.+章[^_\-—]*)", title)
        if match:
            return match.group(1).strip()

    return None


def parse_chapters(html_content: str, base_url: str = "") -> Dict[int, Dict[str, str]]:
    """
    Parse <ul class="chapter"> into {chapter_number: {'url': full_url, 'title': title}}
    Supports both Arabic and Chinese numerals in chapter titles.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    chapters: Dict[int, Dict[str, str]] = {}
    ul = soup.find("ul", class_="chapter")
    if not ul:
        return chapters

    for a_tag in ul.find_all("a", href=True):
        raw_text = html_unescape.unescape(a_tag.get_text(strip=True))
        href = a_tag["href"]
        chapter_num = chapter_title_to_number(raw_text)
        if chapter_num:
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
                last_chapter_number = chapter_title_to_number(last_chapter_title)

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
        href = chapter_tag.get("href", "") if chapter_tag else ""
        lasturl = urljoin(base_url or "", href) if href else ""

        intro_tag = box.select_one("div.bookinfo div.intro_line")
        intro_text = intro_tag.get_text(" ", strip=True) if intro_tag else ""
        intro = intro_text.replace("簡介：", "").replace("简介：", "").strip()

        out.append(
            {
                "bookname": bookname,
                "author": author,
                "lastchapter": lastchapter,
                "lasturl": lasturl,
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


# def resolve_book_home(book_id: str) -> str:
#     return f"{BASE_URL}/{book_id}/"


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


# -----------------------
# Liebiao parsing
# -----------------------
def chinese_to_arabic(chinese_num: str) -> Optional[int]:
    """
    Convert Chinese numerals to Arabic numerals.
    Examples:
        '六百八十' -> 680
        '一千二百三十四' -> 1234
        '三十' -> 30
        '五' -> 5
        '十' -> 10
        '一万' -> 10000
    """
    # Chinese digit mapping
    chinese_digits = {
        '零': 0, '〇': 0,
        '一': 1, '壹': 1,
        '二': 2, '贰': 2, '貳': 2, '两': 2, '兩': 2,
        '三': 3, '叁': 3, '參': 3,
        '四': 4, '肆': 4,
        '五': 5, '伍': 5,
        '六': 6, '陆': 6, '陸': 6,
        '七': 7, '柒': 7,
        '八': 8, '捌': 8,
        '九': 9, '玖': 9,
    }

    # Chinese unit mapping
    chinese_units = {
        '十': 10, '拾': 10,
        '百': 100, '佰': 100,
        '千': 1000, '仟': 1000,
        '万': 10000, '萬': 10000,
    }

    result = 0
    section = 0  # Current section value (before hitting 万)
    temp_num = 0  # Temporary number before unit

    i = 0
    while i < len(chinese_num):
        char = chinese_num[i]

        if char in chinese_digits:
            temp_num = chinese_digits[char]
            i += 1
        elif char in chinese_units:
            unit_value = chinese_units[char]

            # Special case: 十 at the beginning (e.g., 十五 = 15, 十 = 10)
            if unit_value == 10 and temp_num == 0 and section == 0 and result == 0:
                temp_num = 1

            if unit_value == 10000:  # 万
                # Complete the current section and multiply by 万
                section = (section + temp_num) if temp_num > 0 else section
                result += section * unit_value
                section = 0
                temp_num = 0
            else:
                # Regular units (十, 百, 千)
                section += temp_num * unit_value
                temp_num = 0
            i += 1
        else:
            # Skip unknown characters
            i += 1

    # Add remaining values
    result += section + temp_num
    return result if result > 0 else None


def chapter_title_to_number(title: str) -> Optional[int]:
    """
    Extract numeric chapter index from chapter titles.
    Supports both Arabic and Chinese numerals:
        '第1199章 XXX' -> 1199
        '第六百八十章 XXX' -> 680
        '第一千二百三十四章 XXX' -> 1234
    """
    # Try Arabic numerals first
    m = re.search(r"第\s*(\d+)\s*章", title)
    if m:
        return int(m.group(1))

    # Try Chinese numerals
    m = re.search(r"第\s*([零〇一二三四五六七八九十百千万壹贰貳叁參肆伍陆陸柒捌玖拾佰仟萬兩两]+)\s*章", title)
    if m:
        chinese_num = m.group(1)
        return chinese_to_arabic(chinese_num)

    return None

def fetch_chapters_from_liebiao(html_content: str, page_url: str, base_site: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parse <div class="liebiao"> chapter list.
    - `page_url` should be the book HOME URL (so relative hrefs join correctly)
    - Rewrites final URLs to the canonical site host to avoid mixing m/www

    Returns: [{ 'url': absolute_url, 'title': str, 'number': int|None }, ...]
    """
    soup = BeautifulSoup(html_content, "html.parser")
    container = soup.find("div", class_="liebiao")
    if not container:
        return []

    base_site = base_site or canonical_base()

    out: List[Dict[str, Any]] = []
    for a_tag in container.select("ul li a[href]"):
        href = a_tag["href"]
        title = a_tag.get_text(strip=True)
        # join using the page URL (book home) to keep folder context intact
        absolute = urljoin(page_url, href)
        # rewrite host to canonical (prevents mixing m/www)
        absolute = rewrite_to_canonical(absolute)
        out.append({
            "url": absolute,
            "title": title,
            "number": chapter_title_to_number(title),
        })
    return out

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
    lasturl: str
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
app = FastAPI(
    title="小說網 API",
    version="1.0.0",
    root_path="/xsw/api"  # This adds /api as a prefix for all routes
)

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
    www: bool = Query(False),
):
    """
    Chapters are fetched ONLY from <div class="liebiao"> on the book HOME page.
    - all=true: return the full list
    - all=false: return a server-side paginated slice (CHAPTERS_PAGE_SIZE)
    """
    if www:
        try:
            home_url = resolve_book_home(book_id)

            # Try cached full list
            all_key = (book_id, "liebiao", "ALL")
            if not nocache:
                cached = chapters_all_cache.get(all_key)
                if cached is not None:
                    all_chapters: List[ChapterRef] = cached
                else:
                    html_content = fetch_html(home_url)
                    raw = fetch_chapters_from_liebiao(html_content, page_url=home_url)
                    # warm mapping cache
                    for item in raw:
                        if item.get("number") is not None:
                            chapter_url_cache.set((book_id, item["number"]), item["url"])
                    all_chapters = [
                        ChapterRef(number=item.get("number"), title=item["title"], url=item["url"])
                        for item in raw
                    ]
                    chapters_all_cache.set(all_key, all_chapters)
            else:
                html_content = fetch_html(home_url)
                raw = fetch_chapters_from_liebiao(html_content, page_url=home_url)
                for item in raw:
                    if item.get("number") is not None:
                        chapter_url_cache.set((book_id, item["number"]), item["url"])
                all_chapters = [
                    ChapterRef(number=item.get("number"), title=item["title"], url=item["url"])
                    for item in raw
                ]

            if all:
                return all_chapters

            # server-side pagination
            total = len(all_chapters)
            total_pages = max(1, ceil(total / CHAPTERS_PAGE_SIZE))
            current_page = min(max(page, 1), total_pages)

            page_key = (book_id, "liebiao", current_page)
            if not nocache:
                cached_page = chapters_page_cache.get(page_key)
                if cached_page is not None:
                    return cached_page

            start = (current_page - 1) * CHAPTERS_PAGE_SIZE
            end = start + CHAPTERS_PAGE_SIZE
            slice_chapters = all_chapters[start:end]

            chapters_page_cache.set(page_key, slice_chapters)
            return slice_chapters

        except requests.HTTPError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


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

        result = {"chapters":[
            ChapterRef(number=k, title=v["title"], url=v["url"])
            for k, v in sorted(merged.items())
        ], "totalPages": effective_pages}
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
    www: bool = Query(False),
):
    """
    Resolve chapter URL via liebiao list (book HOME).
    Uses mapping cache for fast lookups. Extracts content with robust id fallbacks.
    """
    if www:
        try:
            # 1) mapping cache shortcut
            if not nocache:
                cached_url = chapter_url_cache.get((book_id, chapter_num))
                if cached_url:
                    chapter_html = fetch_html(cached_url)
                    text = (
                        extract_text_by_id(chapter_html, "nr1")
                        or extract_text_by_id(chapter_html, "nr")
                        or extract_text_by_id(chapter_html, "content")
                    )
                    if not text:
                        raise HTTPException(status_code=404, detail=f"No content found in {cached_url}")
                    # Recover title from liebiao
                    home_html = fetch_html(resolve_book_home(book_id))
                    items = fetch_chapters_from_liebiao(home_html, page_url=resolve_book_home(book_id))
                    title = next((it["title"] for it in items if it.get("number") == chapter_num), None)
                    return ChapterContent(book_id=book_id, chapter_num=chapter_num, title=title, url=cached_url, text=text)

            # 2) load liebiao, warm caches, find target
            home_url = resolve_book_home(book_id)
            home_html = fetch_html(home_url)
            items = fetch_chapters_from_liebiao(home_html, page_url=home_url)

            target = next((it for it in items if it.get("number") == chapter_num), None)
            if not target:
                raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")

            for it in items:
                num = it.get("number")
                if num is not None:
                    chapter_url_cache.set((book_id, num), it["url"])

            chapter_html = fetch_html(target["url"])
            text = (
                extract_text_by_id(chapter_html, "nr1")
                or extract_text_by_id(chapter_html, "nr")
                or extract_text_by_id(chapter_html, "content")
            )
            if not text:
                raise HTTPException(status_code=404, detail=f"No content found in {target['url']}")

            return ChapterContent(book_id=book_id, chapter_num=chapter_num, title=target["title"], url=target["url"], text=text)

        except requests.HTTPError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
