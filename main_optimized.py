# main_optimized.py
"""
Optimized FastAPI backend with SQLite database-first caching.
Strategy: Check DB → Fetch from web → Store to DB
"""
import asyncio
import time
from typing import Any, List, Optional
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from db_models import init_database
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Request, Depends, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import requests
import os
import shutil
import uuid
import threading
from pathlib import Path
import urllib3
import logging


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
    extract_text_by_selector,
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
from user_auth import (
    verify_google_user,
    verify_facebook_user,
    verify_apple_user,
    verify_wechat_user,
    find_or_create_user,
    build_auth_response,
    require_user_auth,
    optional_user_auth,
    UserAuthResponse,
    UserProfile,
    UserTokenPayload,
)
import analytics
from db_models import User, ReadingProgress, Comment

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# -----------------------
# Configuration
# -----------------------
BASE_URL = os.getenv("BASE_URL", "https://czbooks.net")
WWW_BASE = os.getenv("WWW_BASE", "https://czbooks.net")
DEFAULT_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))
DB_PATH = os.getenv("DB_PATH", "xsw_cache.db")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "900"))

# Rate limiting configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_WHITELIST = os.getenv("RATE_LIMIT_WHITELIST", "127.0.0.1,::1").split(",")

# Use curl_cffi to bypass Cloudflare TLS fingerprinting (JA3).
# Falls back to standard requests if curl_cffi is unavailable.
try:
    from curl_cffi.requests import Session as CffiSession
    _cffi_session = CffiSession(impersonate="chrome")
    _use_cffi = True
    print("[init] Using curl_cffi with Chrome TLS impersonation")
except ImportError:
    _cffi_session = None
    _use_cffi = False
    print("[init] curl_cffi not available, using standard requests")

session = requests.Session()
session.headers.update({
    "User-Agent": "curl/8.14.1",
    "Accept": "*/*",
})


# Per-book locks to prevent concurrent web fetches of the same book
_book_fetch_locks: dict[str, threading.Lock] = {}
_book_fetch_locks_guard = threading.Lock()


def _get_book_lock(book_id: str) -> threading.Lock:
    """Get or create a lock for a specific book_id."""
    with _book_fetch_locks_guard:
        if book_id not in _book_fetch_locks:
            _book_fetch_locks[book_id] = threading.Lock()
        return _book_fetch_locks[book_id]


# -----------------------
# Helper Functions
# -----------------------
def canonical_base() -> str:
    """Return the canonical scheme+host."""
    from urllib.parse import urlparse
    p = urlparse(BASE_URL)
    return f"{p.scheme}://{p.netloc}"


def resolve_book_home(book_id: str) -> str:
    """Resolve book home URL. czbooks.net uses /n/{book_id}."""
    base = canonical_base()
    return f"{base}/n/{book_id}"


PROXY_URL = os.getenv("HTTP_PROXY_URL", "http://taleon.work.gd:55128")

def fetch_html(url: str) -> str:
    """
    Fetch HTML with Cloudflare bypass.
    Uses curl_cffi (Chrome TLS fingerprint) when available,
    falls back to standard requests.
    """
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

    if _use_cffi and _cffi_session:
        resp = _cffi_session.get(url, timeout=DEFAULT_TIMEOUT, verify=False, proxies=proxies)
        resp.raise_for_status()
        return resp.text

    resp = session.get(url, timeout=DEFAULT_TIMEOUT, verify=False, proxies=proxies)
    resp.raise_for_status()
    enc = resp.apparent_encoding or resp.encoding or "utf-8"
    resp.encoding = enc
    return resp.text


# -----------------------
# ID Resolution Helpers
# -----------------------
def resolve_book_id(input_id: str) -> str:
    """
    Resolve public_id or czbooks_id to internal czbooks book_id.
    Accepts both our public IDs and original czbooks IDs (transparent resolution).
    """
    import db_models as _db
    from db_models import Book

    if not _db.db_manager:
        return input_id

    session = _db.db_manager.get_session()
    try:
        # Try public_id first
        book = session.query(Book).filter(Book.public_id == input_id).first()
        if book:
            return book.id  # return czbooks ID
        # Fall back to czbooks ID directly
        return input_id
    except Exception:
        # SQLite concurrent access may corrupt session — fall back gracefully
        return input_id
    finally:
        session.close()


def resolve_chapter(book_czid: str, chapter_input: str) -> tuple:
    """
    Resolve chapter public_id to (book_czid, chapter_num).
    Falls back to treating input as sequential number.
    """
    import db_models as _db
    from db_models import Chapter

    if not _db.db_manager:
        return book_czid, int(chapter_input)

    session = _db.db_manager.get_session()
    try:
        ch = (
            session.query(Chapter)
            .filter(Chapter.book_id == book_czid, Chapter.public_id == chapter_input)
            .first()
        )
        if ch:
            return book_czid, ch.chapter_num
        # Fall back: treat as sequential number
        return book_czid, int(chapter_input)
    except ValueError:
        # Not a valid integer and not a known public_id
        return book_czid, -1
    finally:
        session.close()


# Lock for serializing public_id creation to prevent SQLite concurrent write issues
_public_id_lock = threading.Lock()


def get_book_public_id(
    book_czid: str,
    book_name: str = "",
    author: str = "",
    book_type: str = "",
    last_chapter_title: str = "",
    last_chapter_url: str = "",
    bookmark_count: Optional[int] = None,
    view_count: Optional[int] = None,
) -> Optional[str]:
    """Get or create a public_id for a book given its czbooks ID.

    If the book exists in DB, returns its public_id (and updates stats if provided).
    Fields like author/type/last_chapter are only filled in when the DB value is
    currently NULL/empty, so richer data from the book detail page is never overwritten.
    If the book doesn't exist, creates a minimal record with a public_id.

    Serialized with a lock to prevent SQLite concurrent write corruption when
    many category listing requests hit simultaneously.
    """
    import db_models as _db
    from db_models import Book
    from cache_manager import generate_public_id

    if not _db.db_manager:
        return None

    with _public_id_lock:
        session = _db.db_manager.get_session()
        try:
            book = session.query(Book).filter(Book.id == book_czid).first()
            if book:
                changed = False
                if not book.public_id:
                    book.public_id = generate_public_id()
                    changed = True
                if bookmark_count is not None:
                    book.bookmark_count = bookmark_count
                    changed = True
                if view_count is not None:
                    book.view_count = view_count
                    changed = True
                # Back-fill fields only when DB value is empty
                if author and not book.author:
                    book.author = author
                    changed = True
                if book_type and not book.type:
                    book.type = book_type
                    changed = True
                if last_chapter_title and not book.last_chapter_title:
                    book.last_chapter_title = last_chapter_title
                    changed = True
                if last_chapter_url and not book.last_chapter_url:
                    book.last_chapter_url = last_chapter_url
                    changed = True
                if changed:
                    session.commit()
                return book.public_id

            # Book not in DB yet — create a minimal record so it gets a public_id
            pub_id = generate_public_id()
            book = Book(
                id=book_czid,
                public_id=pub_id,
                name=book_name or book_czid,
                author=author or None,
                type=book_type or None,
                last_chapter_title=last_chapter_title or None,
                last_chapter_url=last_chapter_url or None,
                bookmark_count=bookmark_count,
                view_count=view_count,
            )
            session.add(book)
            session.commit()
            return pub_id
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            print(f"[API] Error getting/creating public_id for {book_czid}: {e}")
            return None
        finally:
            session.close()


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
    public_id: Optional[str] = None
    bookmark_count: Optional[int] = None
    view_count: Optional[int] = None


# -----------------------
# FastAPI App with Lifespan
# -----------------------
def _backfill_public_ids():
    """Add public_id columns if missing (migration) and backfill NULLs."""
    import db_models as _db
    from sqlalchemy import inspect as sa_inspect, text as sa_text

    if not _db.db_manager:
        return

    # Migrate: add columns if they don't exist yet
    engine = _db.db_manager.engine
    inspector = sa_inspect(engine)
    with engine.connect() as conn:
        book_cols = {c["name"] for c in inspector.get_columns("books")}
        if "public_id" not in book_cols:
            conn.execute(sa_text("ALTER TABLE books ADD COLUMN public_id TEXT"))
            conn.execute(sa_text("CREATE UNIQUE INDEX IF NOT EXISTS ix_books_public_id ON books (public_id)"))
            conn.commit()
            print("[Migration] Added public_id column to books table")

        if "description" not in book_cols:
            conn.execute(sa_text("ALTER TABLE books ADD COLUMN description TEXT"))
            conn.commit()
            print("[Migration] Added description column to books table")

        if "bookmark_count" not in book_cols:
            conn.execute(sa_text("ALTER TABLE books ADD COLUMN bookmark_count INTEGER"))
            conn.commit()
            print("[Migration] Added bookmark_count column to books table")

        if "view_count" not in book_cols:
            conn.execute(sa_text("ALTER TABLE books ADD COLUMN view_count INTEGER"))
            conn.commit()
            print("[Migration] Added view_count column to books table")

        ch_cols = {c["name"] for c in inspector.get_columns("chapters")}
        if "public_id" not in ch_cols:
            conn.execute(sa_text("ALTER TABLE chapters ADD COLUMN public_id TEXT"))
            conn.execute(sa_text("CREATE UNIQUE INDEX IF NOT EXISTS ix_chapters_public_id ON chapters (public_id)"))
            conn.commit()
            print("[Migration] Added public_id column to chapters table")

    # Use raw SQL for fast bulk backfill — Python-level ORM is too slow for 1M+ rows
    with engine.connect() as conn:
        # Backfill books
        result = conn.execute(sa_text(
            "UPDATE books SET public_id = lower(hex(randomblob(5))) WHERE public_id IS NULL"
        ))
        if result.rowcount:
            conn.commit()
            print(f"[Backfill] Assigned public_id to {result.rowcount} books")

        # Backfill chapters
        result = conn.execute(sa_text(
            "UPDATE chapters SET public_id = lower(hex(randomblob(5))) WHERE public_id IS NULL"
        ))
        if result.rowcount:
            conn.commit()
            print(f"[Backfill] Assigned public_id to {result.rowcount} chapters")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup: Initialize database and cache
    print(f"[App] Starting with BASE_URL={BASE_URL}, DB_PATH={DB_PATH}")
    init_database(f"sqlite:///{DB_PATH}")
    init_cache_manager(ttl_seconds=CACHE_TTL)

    # Backfill public_id for existing rows
    _backfill_public_ids()

    # Initialize admin users
    from auth import init_admin_users
    import db_models
    if db_models.db_manager:
        init_admin_users(db_models.db_manager)

    # Initialize analytics (separate SQLite DB) and start background writer
    analytics.init_db()
    analytics.start_writer()

    print("[App] Database, cache, auth, and analytics initialized")

    yield  # Application runs here

    # Shutdown: Cleanup
    print("[App] Shutting down...")
    analytics.stop_writer()
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

# -----------------------
# HTTP Cache-Control Middleware
# -----------------------
import re

# Route patterns → max-age in seconds (only for GET, only for 2xx responses)
_CACHE_RULES: list[tuple[re.Pattern, int]] = [
    # Chapter content — immutable once fetched, cache aggressively
    (re.compile(r"^/xsw/api/books/[^/]+/chapters/[^/]+$"), 86400),   # 1 day
    # Book info — changes when new chapters appear
    (re.compile(r"^/xsw/api/books/[^/]+$"), 300),                    # 5 min
    # Chapter list
    (re.compile(r"^/xsw/api/books/[^/]+/chapters$"), 300),           # 5 min
    # Similar books / author books
    (re.compile(r"^/xsw/api/books/[^/]+/similar$"), 3600),           # 1 hour
    (re.compile(r"^/xsw/api/authors/[^/]+/books$"), 3600),           # 1 hour
    # Comments list (not mutations)
    (re.compile(r"^/xsw/api/books/[^/]+/comments$"), 60),            # 1 min
    # Categories — very stable
    (re.compile(r"^/xsw/api/categories$"), 3600),                    # 1 hour
    (re.compile(r"^/xsw/api/categories/[^/]+/books$"), 300),         # 5 min
    # Search results
    (re.compile(r"^/xsw/api/search$"), 60),                          # 1 min
    # by-url helpers
    (re.compile(r"^/xsw/api/by-url/"), 300),                         # 5 min
]


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control headers on cacheable GET responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only cache successful GET responses that don't already have Cache-Control
        if (
            request.method != "GET"
            or response.status_code < 200
            or response.status_code >= 300
            or "cache-control" in response.headers
        ):
            return response

        path = request.url.path
        for pattern, max_age in _CACHE_RULES:
            if pattern.match(path):
                response.headers["Cache-Control"] = f"public, max-age={max_age}"
                break
        else:
            # Admin, auth, user endpoints and everything else: don't cache
            if "/admin/" in path or "/user/" in path or "/auth/" in path:
                response.headers["Cache-Control"] = "private, no-store"

        return response

app.add_middleware(CacheControlMiddleware)


# Traditional web API — more reliable than openapi endpoint
TPEX_URL = (
    "https://www.tpex.org.tw/web/stock/aftertrading/"
    "daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Simple in-memory cache
_cache: dict[str, Any] = {"data": None, "ts": 0}
CACHE_TTL = 3600  # 1 hour


async def fetch_tpex() -> dict:
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        res = await client.get(TPEX_URL)
        res.raise_for_status()
        data = res.json()

    if data.get("stat") != "ok":
        raise ValueError(f"TPEX returned stat={data.get('stat')}")

    _cache["data"] = data
    _cache["ts"] = now
    return data


def parse_etfs(data: dict) -> list[dict]:
    """Parse ETF rows from TPEX tables response.

    Row format: [code, name, close, change, open, high, low, avg,
                 volume, amount, transactions, lastBid, lastAsk,
                 issuedShares, nextUp, nextDown]
    """
    date = data.get("date", "")
    etfs = []

    for table in data.get("tables", []):
        for row in table.get("data", []):
            if not isinstance(row, list) or len(row) < 11:
                continue
            code = row[0].strip() if row[0] else ""
            if not code.startswith("00"):
                continue

            etfs.append({
                "code": code,
                "name": (row[1] or "").strip(),
                "price": (row[2] or "").strip().replace(",", ""),
                "change": (row[3] or "").strip().replace(",", ""),
                "open": (row[4] or "").strip().replace(",", ""),
                "high": (row[5] or "").strip().replace(",", ""),
                "low": (row[6] or "").strip().replace(",", ""),
                "volume": (row[8] or "").strip().replace(",", ""),
                "transactions": (row[10] or "").strip().replace(",", ""),
                "date": date,
                "source": "tpex",
            })

    return etfs


# Add simple health check at root level (for monitoring)
@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}

# Mount ubike PWA static files (multi-page app)
ubike_dir = "/app/dist/ubike"
if os.path.exists(ubike_dir):
    app.mount("/ubike", StaticFiles(directory=ubike_dir, html=True), name="ubike")
    print(f"[App] Ubike PWA static files mounted at /ubike from {ubike_dir}")

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

    # 5) Social crawler OG meta tags
    SOCIAL_CRAWLERS = ("facebookexternalhit", "Twitterbot", "LinkedInBot", "Line", "Slackbot")

    def _is_social_crawler(user_agent: str) -> bool:
        ua_lower = user_agent.lower()
        return any(c.lower() in ua_lower for c in SOCIAL_CRAWLERS)

    def _build_og_html(title: str, description: str, url: str) -> str:
        import html as html_mod
        t = html_mod.escape(title)
        d = html_mod.escape(description[:200] if description else "")
        u = html_mod.escape(url)
        return f"""<!DOCTYPE html>
<html><head>
<meta property="og:title" content="{t}" />
<meta property="og:description" content="{d}" />
<meta property="og:url" content="{u}" />
<meta property="og:type" content="article" />
<meta name="twitter:card" content="summary" />
<meta name="twitter:title" content="{t}" />
<meta name="twitter:description" content="{d}" />
<title>{t}</title>
</head><body></body></html>"""

    # 6) SPA history-mode fallback:
    #    - Only for paths under "/" that are NOT API calls and NOT obvious assets
    @app.middleware("http")
    async def spa_history_mode_fallback(request: Request, call_next):
        # Check for social crawlers and serve OG meta tags
        ua = request.headers.get("user-agent", "")
        path = request.url.path or ""

        if _is_social_crawler(ua) and not path.startswith("/xsw/api"):
            import re
            # Match /book/{bookId}/chapters or /book/{bookId}/chapter/{chapterId}/{title}
            book_match = re.match(r"^/book/([^/]+)/(chapters|chapter/([^/]+)/?(.*))$", path)
            if book_match:
                book_id = book_match.group(1)
                chapter_title = book_match.group(4) or ""
                try:
                    resolved = resolve_book_id(book_id)
                    book_home_url = resolve_book_home(resolved)
                    html = fetch_html(book_home_url)
                    info = parse_book_info(html, book_home_url)
                    title = info.get("name", "")
                    desc = info.get("description", "") or f"by {info.get('author', '')}"
                    if chapter_title:
                        from urllib.parse import unquote
                        title = f"{title} - {unquote(chapter_title)}"
                    full_url = str(request.url)
                    return Response(
                        content=_build_og_html(title, desc, full_url),
                        media_type="text/html",
                    )
                except Exception:
                    pass  # Fall through to normal SPA serving

        # Let normal routing/StaticFiles try first (APIs, real files, etc.)
        response: Response = await call_next(request)

        if response.status_code != 404:
            return response

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
        "cache_stats": cache_stats, "service": "TPEX Proxy"
    }

@app.get("/tpex/etf-list")
async def tpex_etf_list():
    try:
        data = await fetch_tpex()
    except Exception as e:
        logger.error("TPEX fetch failed: %s", e)
        return JSONResponse(
            status_code=502,
            content={"error": "TPEX fetch failed", "message": str(e)},
        )

    etfs = parse_etfs(data)

    return {
        "count": len(etfs),
        "date": etfs[0]["date"] if etfs else "",
        "etfs": etfs,
    }

@api_router.get("/categories", response_model=List[Category])
def get_categories():
    """Get categories from homepage."""
    try:
        home_url = BASE_URL + "/"
        print(f"[API] Fetching categories from {home_url}")
        html_content = fetch_html(home_url)
        cats = find_categories_from_nav(html_content, BASE_URL)
        print(f"[API] Found {len(cats)} categories")
        result = [Category(**c) for c in cats]
        return result
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        print(f"[API] Exception fetching categories: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/categories/{cat_id}/books", response_model=List[BookSummary])
def list_books_in_category(
    cat_id: str,
    page: int = Query(1, ge=1),
):
    """List books in category (not cached, real-time)."""
    try:
        # czbooks.net: /c/{slug}/{page}  (page 1 is just /c/{slug})
        if page == 1:
            url = f"{BASE_URL}/c/{cat_id}"
        else:
            url = f"{BASE_URL}/c/{cat_id}/{page}"
        html_content = fetch_html(url)
        books = parse_books(html_content, BASE_URL)

        book_summaries = []
        for b in books:
            czid = extract_book_id_from_url(b["bookurl"])
            bm = b.get("bookmark_count")
            vc = b.get("view_count")
            pub_id = get_book_public_id(
                czid,
                b.get("bookname", ""),
                author=b.get("author", ""),
                book_type=cat_id,
                last_chapter_title=b.get("lastchapter", ""),
                last_chapter_url=b.get("lasturl", ""),
                bookmark_count=bm,
                view_count=vc,
            )
            book_summaries.append(
                BookSummary(**b, book_id=czid, public_id=pub_id)
            )

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
    Accepts both public_id and czbooks ID (transparent resolution).

    For unfinished books whose info is older than 12 hours,
    bypass cache and re-fetch from the web.
    """
    try:
        # Resolve public_id to czbooks ID
        czbooks_id = resolve_book_id(book_id)

        # If the book is unfinished and stale (>12h), bypass cache
        stale = cache_mgr.cache_manager.is_book_stale(czbooks_id)
        if stale:
            print(f"[API] Book {czbooks_id} - stale (unfinished, >12h), refreshing")
            cache_mgr.cache_manager.invalidate_book_info(czbooks_id)
        else:
            # Check cache first
            cached_info = cache_mgr.cache_manager.get_book_info(czbooks_id)
            if cached_info:
                print(f"[API] Book {czbooks_id} - cache hit")
                return cached_info

        # Cache miss or stale - fetch from web
        print(f"[API] Book {czbooks_id} - fetching from web")
        url = resolve_book_home(czbooks_id)
        html_content = fetch_html(url)
        info = parse_book_info(html_content, BASE_URL)

        if not info:
            raise HTTPException(status_code=404, detail="Book info not found")

        info["book_id"] = czbooks_id
        info["source_url"] = url

        # Store to cache (DB + memory) — this also assigns public_id
        cache_mgr.cache_manager.store_book_info(czbooks_id, info)

        # Re-read from cache to get the public_id
        cached_info = cache_mgr.cache_manager.get_book_info(czbooks_id)
        if cached_info:
            return cached_info
        return BookInfo(**info)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/books/{book_id}/chapters")
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
    Accepts both public_id and czbooks ID (transparent resolution).

    - www=true: Fetch from home page only (latest ~10 chapters)
    - www=false (default): Fetch from pagination pages (all chapters)
    - all=true: Return all chapters
    - all=false: Return server-side paginated slice (20 chapters per page)
    - page: Page number for server-side pagination (when all=false)
    """
    try:
        # Resolve public_id to czbooks ID
        book_id = resolve_book_id(book_id)
        # First, try to get all chapters from DB or web
        all_chapters = None
        volumes = []  # Volume markers from parser

        if not nocache:
            # Check if we have chapters in DB
            all_chapters = cache_mgr.cache_manager.get_chapter_list(book_id)
            if all_chapters:
                # Validate cached chapters: must start at 1 (sequential indexing)
                # Stale data from old parser may have non-sequential numbers parsed from titles
                first_num = min(c.number for c in all_chapters)
                if first_num != 1:
                    print(f"[API] Chapters for {book_id} - DB stale (first chapter is {first_num}, expected 1), re-fetching")
                    all_chapters = None
                else:
                    print(f"[API] Chapters for {book_id} - DB hit ({len(all_chapters)} chapters)")

        if not all_chapters:
            # Cache miss or nocache - use per-book lock to prevent concurrent fetches
            lock = _get_book_lock(book_id)
            with lock:
                # Re-check cache inside lock (another thread may have filled it)
                if not nocache:
                    all_chapters = cache_mgr.cache_manager.get_chapter_list(book_id)
                    if all_chapters:
                        first_num = min(c.number for c in all_chapters)
                        if first_num == 1:
                            print(f"[API] Chapters for {book_id} - DB hit after lock ({len(all_chapters)} chapters)")
                        else:
                            all_chapters = None

                if not all_chapters:
                    # Still a cache miss - fetch from web
                    print(f"[API] Chapters for {book_id} - fetching from web (www={www})")

                    if www:
                        # Fetch from home page only (mobile site - latest 10 chapters)
                        # NOTE: Don't cache these results as they may be partial and incorrectly numbered
                        home_url = resolve_book_home(book_id)
                        html_content = fetch_html(home_url)
                        items = fetch_chapters_from_liebiao(html_content, home_url, canonical_base(), start_index=1)
                    else:
                        # Fetch from pagination pages (all chapters)
                        volumes = []
                        items = fetch_all_chapters_from_pagination(book_id, volumes_out=volumes)

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

                    # Note: book info (description, stats, last chapter) is already stored
                    # by fetch_all_chapters_from_pagination() for www=false fetches.

        # Return based on 'all' parameter
        if all_chapters_flag:
            # Return chapters with volumes when available
            if volumes:
                return {"chapters": all_chapters, "volumes": volumes}
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


def fetch_all_chapters_from_pagination(book_id: str, volumes_out: list = None) -> list:
    """
    Fetch all chapters for a book.
    czbooks.net lists all chapters on the book detail page (no pagination).
    Also parses and stores book info (description, stats) from the same page.
    If volumes_out is provided, volume markers are captured into it.
    """
    base = canonical_base()
    book_url = f"{base}/n/{book_id}"
    html_content = fetch_html(book_url)

    # czbooks.net has all chapters on a single page in ul.chapter-list
    items = fetch_chapters_from_liebiao(html_content, book_url, base, start_index=1, volumes_out=volumes_out)
    print(f"[API] Fetched {len(items)} chapters for book {book_id} from {book_url}")

    # Parse and store book info from the same HTML (description, bookmark/view counts)
    info = parse_book_info(html_content, BASE_URL)
    if info:
        info["book_id"] = book_id
        info["source_url"] = book_url
        # Preserve last chapter info from the parsed chapters
        if items:
            last = items[-1]
            info["last_chapter_number"] = last["number"]
            info["last_chapter_title"] = last["title"]
            info["last_chapter_url"] = last["url"]
        cache_mgr.cache_manager.store_book_info(book_id, info)

    return items


@api_router.get("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterContent)
def get_chapter_content(
    book_id: str,
    chapter_id: str,
    request: Request,
    nocache: bool = Query(False),
    current_user: Optional[UserTokenPayload] = Depends(optional_user_auth),
):
    """
    Get chapter content.
    Strategy: Check DB → Fetch from web → Store to DB
    Accepts both public_id and czbooks ID for book_id.
    Accepts both chapter public_id and sequential number for chapter_id.
    """
    try:
        # Resolve public_id to czbooks ID
        czbooks_book_id = resolve_book_id(book_id)

        # Resolve chapter_id (public_id or sequential number)
        _, chapter_num = resolve_chapter(czbooks_book_id, chapter_id)
        if chapter_num < 0:
            raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")

        # Track page view (non-blocking)
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.client.host if request.client else None
        analytics.log_page_view(
            book_id=czbooks_book_id,
            chapter_num=chapter_num,
            user_id=current_user.sub if current_user else None,
            ip=client_ip,
            user_agent=request.headers.get("User-Agent"),
            referer=request.headers.get("Referer"),
        )

        if not nocache:
            # Check cache first
            cached_content = cache_mgr.cache_manager.get_chapter_content(czbooks_book_id, chapter_num)
            if cached_content:
                print(f"[API] Chapter {czbooks_book_id}:{chapter_num} - cache hit")
                return cached_content

        # Cache miss - need to fetch
        print(f"[API] Chapter {czbooks_book_id}:{chapter_num} - cache miss, fetching from web")

        # Strategy: Try to get chapter URL from DB first (fastest)
        chapter_url = get_chapter_url_from_db(czbooks_book_id, chapter_num)

        if not chapter_url:
            # Chapter URL not in DB - need to fetch chapter list first
            print(f"[API] Chapter {czbooks_book_id}:{chapter_num} - URL not in DB, fetching chapter list")

            # Try home page first (for recent chapters)
            home_url = resolve_book_home(czbooks_book_id)
            home_html = fetch_html(home_url)
            items = fetch_chapters_from_liebiao(home_html, home_url, canonical_base(), start_index=1)

            # Find target chapter in home page
            target = next((it for it in items if it.get("number") == chapter_num), None)

            if not target:
                # Not in home page - fetch all chapters from pagination
                print(f"[API] Chapter {chapter_num} not in home page, fetching all chapters")
                items = fetch_all_chapters_from_pagination(czbooks_book_id)

                # Store all chapters to DB for future use
                cache_mgr.cache_manager.store_chapter_refs(czbooks_book_id, items)

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
            chapter_title = get_chapter_title_from_db(czbooks_book_id, chapter_num) or f"Chapter {chapter_num}"
            print(f"[API] Chapter {czbooks_book_id}:{chapter_num} - found URL in DB: {chapter_url}")

        # Fetch chapter content
        chapter_html = fetch_html(chapter_url)
        # Try czbooks.net selector first, then fall back to legacy selectors
        text = (
            extract_text_by_selector(chapter_html, ".chapter-detail div.content")
            or extract_text_by_id(chapter_html, "nr1")
            or extract_text_by_id(chapter_html, "nr")
            or extract_text_by_id(chapter_html, "content")
        )

        if not text:
            raise HTTPException(
                status_code=404, detail=f"No content found in {chapter_url}"
            )

        # Store to cache (DB + memory) — this also assigns chapter public_id
        content_data = {
            "title": chapter_title,
            "url": chapter_url,
            "text": text,
        }
        cache_mgr.cache_manager.store_chapter_content(czbooks_book_id, chapter_num, content_data)

        # Re-read from cache to get the chapter_id (public_id)
        cached = cache_mgr.cache_manager.get_chapter_content(czbooks_book_id, chapter_num)
        if cached:
            return cached

        return ChapterContent(
            book_id=czbooks_book_id,
            chapter_num=chapter_num,
            title=chapter_title,
            url=chapter_url,
            text=text,
        )
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except HTTPException:
        raise
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
    public_id: Optional[str] = None  # book public_id
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
                            public_id=book.public_id,
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
                    # Get book public_id for the result
                    book_pub_id = get_book_public_id(chapter.book_id)
                    results.append(
                        SearchResult(
                            book_id=chapter.book_id,
                            public_id=book_pub_id,
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

                    book_pub_id = get_book_public_id(chapter.book_id)
                    results.append(
                        SearchResult(
                            book_id=chapter.book_id,
                            public_id=book_pub_id,
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

        # Filter out legacy numeric book IDs (old m.xsw.tw data) that can't be
        # resolved on czbooks.net.  czbooks IDs are alphanumeric (e.g. "s660jj").
        results = [r for r in results if not r.book_id.isdigit()]

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
                    "public_id": result.public_id,
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
    book_id = resolve_book_id(book_id)
    cache_mgr.cache_manager.invalidate_book(book_id)
    return {"status": "invalidated", "book_id": book_id, "scope": "memory_only"}


@api_router.delete("/admin/cache/chapters/{book_id}")
def delete_book_chapters_cache(book_id: str, auth: TokenPayload = Depends(require_admin_auth)):
    """Delete all chapter records for a book from database and memory cache."""
    book_id = resolve_book_id(book_id)
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
    Fetch chapters by raw book URL.
    czbooks.net: all chapters are on the book detail page.
    """
    try:
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
        # Try czbooks selector first, then legacy
        text = (
            extract_text_by_selector(chapter_html, ".chapter-detail div.content")
            or extract_text_by_id(chapter_html, "nr1")
            or extract_text_by_id(chapter_html, "nr")
            or extract_text_by_id(chapter_html, "content")
        )

        # Extract book_id from URL (czbooks: /n/{book_id}/{chapter_id})
        book_id = extract_book_id_from_url(chapter_url)

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
# User Authentication Endpoints
# -----------------------
class GoogleUserLoginRequest(BaseModel):
    id_token: str

class FacebookUserLoginRequest(BaseModel):
    access_token: str

class AppleUserLoginRequest(BaseModel):
    id_token: str
    authorization_code: Optional[str] = None

class WeChatUserLoginRequest(BaseModel):
    code: str


@api_router.post("/user/auth/google", response_model=UserAuthResponse)
def user_login_google(req: GoogleUserLoginRequest):
    """Login/register with Google for regular users."""
    try:
        info = verify_google_user(req.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        user = find_or_create_user(
            db,
            provider="google",
            provider_user_id=info["provider_user_id"],
            email=info["email"],
            name=info["name"],
            avatar=info["avatar"],
        )
        return build_auth_response(user)
    finally:
        db.close()


@api_router.post("/user/auth/facebook", response_model=UserAuthResponse)
def user_login_facebook(req: FacebookUserLoginRequest):
    """Login/register with Facebook for regular users."""
    try:
        info = verify_facebook_user(req.access_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        user = find_or_create_user(
            db,
            provider="facebook",
            provider_user_id=info["provider_user_id"],
            email=info["email"],
            name=info["name"],
            avatar=info["avatar"],
        )
        return build_auth_response(user)
    finally:
        db.close()


@api_router.post("/user/auth/apple", response_model=UserAuthResponse)
def user_login_apple(req: AppleUserLoginRequest):
    """Login/register with Apple for regular users."""
    try:
        info = verify_apple_user(req.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        user = find_or_create_user(
            db,
            provider="apple",
            provider_user_id=info["provider_user_id"],
            email=info["email"],
            name=info["name"],
            avatar=info["avatar"],
        )
        return build_auth_response(user)
    finally:
        db.close()


@api_router.post("/user/auth/wechat", response_model=UserAuthResponse)
def user_login_wechat(req: WeChatUserLoginRequest):
    """Login/register with WeChat for regular users."""
    try:
        info = verify_wechat_user(req.code)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        user = find_or_create_user(
            db,
            provider="wechat",
            provider_user_id=info["provider_user_id"],
            email=info["email"],
            name=info["name"],
            avatar=info["avatar"],
            access_token=info.get("access_token"),
            refresh_token=info.get("refresh_token"),
        )
        return build_auth_response(user)
    finally:
        db.close()


@api_router.get("/user/auth/verify")
def user_verify_token(auth: UserTokenPayload = Depends(require_user_auth)):
    """Verify user JWT token."""
    return {"valid": True, "user_id": auth.sub, "display_name": auth.display_name}


@api_router.get("/user/auth/me", response_model=UserProfile)
def user_get_profile(auth: UserTokenPayload = Depends(require_user_auth)):
    """Get current user profile."""
    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        user = db.query(User).filter(User.id == auth.sub).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return UserProfile(
            id=user.id,
            display_name=user.display_name,
            email=user.email,
            avatar_url=user.avatar_url,
        )
    finally:
        db.close()


# -----------------------
# Reading Progress Endpoints
# -----------------------
class ProgressUpdateRequest(BaseModel):
    chapter_number: int
    chapter_title: Optional[str] = None
    chapter_id: Optional[str] = None
    book_name: Optional[str] = None
    scroll_position: Optional[int] = 0


class ProgressResponse(BaseModel):
    book_id: str
    book_name: Optional[str] = None
    chapter_number: int
    chapter_title: Optional[str] = None
    chapter_id: Optional[str] = None
    scroll_position: int = 0
    updated_at: str


@api_router.get("/user/progress")
def user_list_progress(auth: UserTokenPayload = Depends(require_user_auth)):
    """List all reading progress for the current user, sorted by most recent."""
    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        progress_list = (
            db.query(ReadingProgress)
            .filter(ReadingProgress.user_id == auth.sub)
            .order_by(ReadingProgress.updated_at.desc())
            .all()
        )
        return [
            ProgressResponse(
                book_id=p.book_id,
                book_name=p.book_name,
                chapter_number=p.chapter_number,
                chapter_title=p.chapter_title,
                chapter_id=p.chapter_id,
                scroll_position=p.scroll_position or 0,
                updated_at=p.updated_at.isoformat() if p.updated_at else "",
            )
            for p in progress_list
        ]
    finally:
        db.close()


@api_router.get("/user/progress/{book_id}")
def user_get_progress(
    book_id: str,
    auth: UserTokenPayload = Depends(require_user_auth),
):
    """Get reading progress for a specific book."""
    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        progress = (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == auth.sub,
                ReadingProgress.book_id == book_id,
            )
            .first()
        )
        if not progress:
            raise HTTPException(status_code=404, detail="No progress found for this book")
        return ProgressResponse(
            book_id=progress.book_id,
            book_name=progress.book_name,
            chapter_number=progress.chapter_number,
            chapter_title=progress.chapter_title,
            chapter_id=progress.chapter_id,
            scroll_position=progress.scroll_position or 0,
            updated_at=progress.updated_at.isoformat() if progress.updated_at else "",
        )
    finally:
        db.close()


@api_router.put("/user/progress/{book_id}")
def user_upsert_progress(
    book_id: str,
    req: ProgressUpdateRequest,
    auth: UserTokenPayload = Depends(require_user_auth),
):
    """Upsert reading progress for a specific book."""
    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        progress = (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == auth.sub,
                ReadingProgress.book_id == book_id,
            )
            .first()
        )
        now = datetime.utcnow()

        if progress:
            progress.chapter_number = req.chapter_number
            progress.chapter_title = req.chapter_title
            progress.chapter_id = req.chapter_id
            progress.book_name = req.book_name or progress.book_name
            progress.scroll_position = req.scroll_position or 0
            progress.updated_at = now
        else:
            progress = ReadingProgress(
                user_id=auth.sub,
                book_id=book_id,
                book_name=req.book_name,
                chapter_number=req.chapter_number,
                chapter_title=req.chapter_title,
                chapter_id=req.chapter_id,
                scroll_position=req.scroll_position or 0,
                updated_at=now,
            )
            db.add(progress)

        db.commit()
        return ProgressResponse(
            book_id=progress.book_id,
            book_name=progress.book_name,
            chapter_number=progress.chapter_number,
            chapter_title=progress.chapter_title,
            chapter_id=progress.chapter_id,
            scroll_position=progress.scroll_position or 0,
            updated_at=progress.updated_at.isoformat() if progress.updated_at else "",
        )
    finally:
        db.close()


@api_router.delete("/user/progress/{book_id}")
def user_delete_progress(
    book_id: str,
    auth: UserTokenPayload = Depends(require_user_auth),
):
    """Delete reading progress for a specific book."""
    import db_models as _db
    db = _db.db_manager.get_session()
    try:
        deleted = (
            db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == auth.sub,
                ReadingProgress.book_id == book_id,
            )
            .delete()
        )
        db.commit()
        if deleted == 0:
            raise HTTPException(status_code=404, detail="No progress found for this book")
        return {"deleted": True}
    finally:
        db.close()


# -----------------------
# Author Pages
# -----------------------
@api_router.get("/authors/{author_name}/books", response_model=List[BookSummary])
def list_books_by_author(author_name: str):
    """List all books by a given author from the database."""
    import db_models as _db
    from db_models import Book

    if not _db.db_manager:
        return []

    session = _db.db_manager.get_session()
    try:
        books = (
            session.query(Book)
            .filter(Book.author == author_name)
            .order_by(Book.view_count.desc().nullslast())
            .all()
        )
        result = []
        for b in books:
            result.append(BookSummary(
                bookname=b.name or "",
                author=b.author or "",
                lastchapter=b.last_chapter_title or "",
                lasturl=b.last_chapter_url or "",
                intro=b.description or "",
                bookurl=b.source_url or "",
                book_id=b.id,
                public_id=b.public_id,
                bookmark_count=b.bookmark_count,
                view_count=b.view_count,
            ))
        return result
    finally:
        session.close()


# -----------------------
# Recommended / Similar Books
# -----------------------
@api_router.get("/books/{book_id}/similar", response_model=List[BookSummary])
def get_similar_books(book_id: str):
    """Get books by the same author or in the same category."""
    import db_models as _db
    from db_models import Book
    from sqlalchemy import or_

    if not _db.db_manager:
        return []

    czbooks_id = resolve_book_id(book_id)
    session = _db.db_manager.get_session()
    try:
        current = session.query(Book).filter(Book.id == czbooks_id).first()
        if not current:
            return []

        conditions = []
        if current.author:
            conditions.append(Book.author == current.author)
        if current.type:
            conditions.append(Book.type == current.type)

        if not conditions:
            return []

        books = (
            session.query(Book)
            .filter(Book.id != czbooks_id, or_(*conditions))
            .order_by(Book.view_count.desc().nullslast())
            .limit(10)
            .all()
        )
        result = []
        for b in books:
            result.append(BookSummary(
                bookname=b.name or "",
                author=b.author or "",
                lastchapter=b.last_chapter_title or "",
                lasturl=b.last_chapter_url or "",
                intro=b.description or "",
                bookurl=b.source_url or "",
                book_id=b.id,
                public_id=b.public_id,
                bookmark_count=b.bookmark_count,
                view_count=b.view_count,
            ))
        return result
    finally:
        session.close()


# -----------------------
# Comments
# -----------------------
class CommentCreateRequest(BaseModel):
    text: str


class CommentResponse(BaseModel):
    id: int
    user_id: int
    display_name: str
    avatar_url: Optional[str] = None
    book_id: str
    text: str
    created_at: str
    updated_at: str


@api_router.get("/books/{book_id}/comments")
def list_book_comments(
    book_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List comments for a book (public, paginated)."""
    import db_models as _db

    if not _db.db_manager:
        return []

    session = _db.db_manager.get_session()
    try:
        offset = (page - 1) * page_size
        rows = (
            session.query(Comment, User)
            .join(User, Comment.user_id == User.id)
            .filter(Comment.book_id == book_id)
            .order_by(Comment.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return [
            CommentResponse(
                id=c.id,
                user_id=c.user_id,
                display_name=u.display_name,
                avatar_url=u.avatar_url,
                book_id=c.book_id,
                text=c.text,
                created_at=c.created_at.isoformat() if c.created_at else "",
                updated_at=c.updated_at.isoformat() if c.updated_at else "",
            )
            for c, u in rows
        ]
    finally:
        session.close()


@api_router.post("/books/{book_id}/comments", status_code=201)
def create_comment(
    book_id: str,
    body: CommentCreateRequest,
    auth: UserTokenPayload = Depends(require_user_auth),
):
    """Create a comment on a book (requires user auth)."""
    import db_models as _db

    text = body.text.strip()
    if not text or len(text) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Comment text must be 1-1000 characters",
        )

    if not _db.db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized")

    session = _db.db_manager.get_session()
    try:
        user = session.query(User).filter(User.id == auth.sub).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        comment = Comment(
            user_id=auth.sub,
            book_id=book_id,
            text=text,
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)

        return CommentResponse(
            id=comment.id,
            user_id=comment.user_id,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            book_id=comment.book_id,
            text=comment.text,
            created_at=comment.created_at.isoformat() if comment.created_at else "",
            updated_at=comment.updated_at.isoformat() if comment.updated_at else "",
        )
    finally:
        session.close()


@api_router.delete("/user/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    auth: UserTokenPayload = Depends(require_user_auth),
):
    """Delete own comment (requires user auth)."""
    import db_models as _db

    if not _db.db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized")

    session = _db.db_manager.get_session()
    try:
        comment = session.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        if comment.user_id != auth.sub:
            raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
        session.delete(comment)
        session.commit()
        return {"deleted": True}
    finally:
        session.close()


# -----------------------
# Admin Analytics Endpoints
# -----------------------

@api_router.get("/admin/analytics/summary")
def analytics_summary(auth: TokenPayload = Depends(require_admin_auth)):
    """Total views, unique visitors, today/week/month counts, top 5 books."""
    session = analytics.get_session()
    try:
        return analytics.get_summary(session)
    finally:
        session.close()


@api_router.get("/admin/analytics/books/{book_id}")
def analytics_book(
    book_id: str,
    days: int = Query(30, ge=1, le=365),
    auth: TokenPayload = Depends(require_admin_auth),
):
    """Per-book analytics: daily views (N days), top chapters."""
    session = analytics.get_session()
    try:
        return analytics.get_book_analytics(session, book_id, days)
    finally:
        session.close()


@api_router.get("/admin/analytics/top")
def analytics_top_books(
    period: str = Query("week"),
    limit: int = Query(20, ge=1, le=100),
    auth: TokenPayload = Depends(require_admin_auth),
):
    """Top books by views within a time period (day/week/month/all)."""
    session = analytics.get_session()
    try:
        return analytics.get_top_books(session, period, limit)
    finally:
        session.close()


@api_router.get("/admin/analytics/traffic")
def analytics_traffic(
    days: int = Query(30, ge=1, le=365),
    auth: TokenPayload = Depends(require_admin_auth),
):
    """Daily views + unique visitors chart data."""
    session = analytics.get_session()
    try:
        return analytics.get_traffic(session, days)
    finally:
        session.close()


@api_router.post("/admin/analytics/cleanup")
def analytics_cleanup(
    days: int = Query(90, ge=1),
    auth: TokenPayload = Depends(require_admin_auth),
):
    """Delete page views older than N days."""
    session = analytics.get_session()
    try:
        deleted = analytics.cleanup_old_views(session, days)
        return {"deleted": deleted, "older_than_days": days}
    finally:
        session.close()


# -----------------------
# Include API Router
# -----------------------
# IMPORTANT: This must be done AFTER all route definitions above
app.include_router(api_router, prefix="/xsw/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
