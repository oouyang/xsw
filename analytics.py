# analytics.py
"""
Lightweight analytics for tracking chapter reads.

Uses a **separate SQLite database** to isolate analytics writes from the
main cache DB, avoiding write contention.

- Background writer thread batches inserts to reduce SQLite write contention.
- log_page_view() is non-blocking; silently drops if queue is full.
- Query helpers power the admin analytics endpoints.
"""
import hashlib
import os
import queue
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Index,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import text as sql_text

# ---------------------------------------------------------------------------
# Separate declarative base — analytics tables live in their own DB
# ---------------------------------------------------------------------------
AnalyticsBase = declarative_base()


class PageView(AnalyticsBase):
    """Analytics: page view events for chapter reads."""

    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(String, nullable=False, index=True)
    chapter_num = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    ip_hash = Column(String(16), nullable=True)
    user_agent_hash = Column(String(16), nullable=True)
    referer = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_pv_book_created", "book_id", "created_at"),
    )

    def __repr__(self):
        return f"<PageView(book_id='{self.book_id}', chapter_num={self.chapter_num})>"


# ---------------------------------------------------------------------------
# Database management (separate from main db_models.DatabaseManager)
# ---------------------------------------------------------------------------
_engine = None
_SessionLocal = None


def init_db(db_url: str = None):
    """Initialize the analytics database (separate SQLite file)."""
    global _engine, _SessionLocal

    if db_url is None:
        db_path = os.getenv("ANALYTICS_DB_PATH", "xsw_analytics.db")
        db_url = f"sqlite:///{db_path}"

    _engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
    )

    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    # Create tables
    AnalyticsBase.metadata.create_all(bind=_engine)

    # Enable WAL mode for better concurrency
    if db_url.startswith("sqlite") and ":memory:" not in db_url:
        with _engine.connect() as conn:
            conn.execute(sql_text("PRAGMA journal_mode=WAL"))
            conn.execute(sql_text("PRAGMA synchronous=NORMAL"))
            conn.commit()

    print(f"[Analytics] Database initialized: {db_url}")


def get_session() -> Session:
    """Get a new analytics database session."""
    if _SessionLocal is None:
        raise RuntimeError("Analytics DB not initialized. Call analytics.init_db() first.")
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Hashing helpers (privacy: truncated SHA-256)
# ---------------------------------------------------------------------------

def _hash16(value: str) -> str:
    """Return first 16 hex chars of SHA-256 digest."""
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def hash_ip(ip: str) -> str:
    return _hash16(ip)


def hash_user_agent(ua: str) -> str:
    return _hash16(ua)


# ---------------------------------------------------------------------------
# Background writer
# ---------------------------------------------------------------------------

_queue: queue.Queue = queue.Queue(maxsize=10000)
_stop_event = threading.Event()
_writer_thread: Optional[threading.Thread] = None

BATCH_SIZE = 50
FLUSH_INTERVAL = 5.0  # seconds


def _writer_loop():
    """Drain the queue in batches and write to the database."""
    buf = []
    last_flush = time.monotonic()

    while not _stop_event.is_set():
        # Drain available items (non-blocking after first)
        try:
            item = _queue.get(timeout=0.5)
            buf.append(item)
        except queue.Empty:
            pass

        # Flush when batch is full or interval elapsed
        now = time.monotonic()
        if buf and (len(buf) >= BATCH_SIZE or now - last_flush >= FLUSH_INTERVAL):
            _flush(buf)
            buf = []
            last_flush = now

    # Final flush on shutdown
    while not _queue.empty():
        try:
            buf.append(_queue.get_nowait())
        except queue.Empty:
            break
    if buf:
        _flush(buf)


def _flush(buf: list[dict]):
    """Insert a batch of page view records."""
    session = get_session()
    try:
        session.bulk_insert_mappings(PageView, buf)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Analytics] Flush error: {e}")
    finally:
        session.close()


def start_writer():
    """Start the background writer daemon thread."""
    global _writer_thread
    _stop_event.clear()
    _writer_thread = threading.Thread(
        target=_writer_loop, daemon=True, name="analytics-writer"
    )
    _writer_thread.start()
    print("[Analytics] Background writer started")


def stop_writer():
    """Signal the writer to stop and wait for it to finish."""
    global _writer_thread
    if _writer_thread is None:
        return
    _stop_event.set()
    _writer_thread.join(timeout=10)
    _writer_thread = None
    print("[Analytics] Background writer stopped")


# ---------------------------------------------------------------------------
# Public logging API
# ---------------------------------------------------------------------------

def log_page_view(
    book_id: str,
    chapter_num: Optional[int] = None,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None,
):
    """Enqueue a page view. Non-blocking; drops silently if queue full."""
    record = {
        "book_id": book_id,
        "chapter_num": chapter_num,
        "user_id": user_id,
        "ip_hash": hash_ip(ip) if ip else None,
        "user_agent_hash": hash_user_agent(user_agent) if user_agent else None,
        "referer": referer,
        "created_at": datetime.utcnow(),
    }
    try:
        _queue.put_nowait(record)
    except queue.Full:
        pass  # silently drop


# ---------------------------------------------------------------------------
# Query helpers (called from admin endpoints)
# ---------------------------------------------------------------------------

def get_summary(session: Session) -> dict:
    """Total views, unique visitors, today/week/month counts, top 5 books."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    total_views = session.query(func.count(PageView.id)).scalar() or 0
    unique_visitors = session.query(func.count(func.distinct(PageView.ip_hash))).scalar() or 0

    today_views = (
        session.query(func.count(PageView.id))
        .filter(PageView.created_at >= today_start)
        .scalar() or 0
    )
    week_views = (
        session.query(func.count(PageView.id))
        .filter(PageView.created_at >= week_start)
        .scalar() or 0
    )
    month_views = (
        session.query(func.count(PageView.id))
        .filter(PageView.created_at >= month_start)
        .scalar() or 0
    )

    top_books = (
        session.query(PageView.book_id, func.count(PageView.id).label("views"))
        .group_by(PageView.book_id)
        .order_by(func.count(PageView.id).desc())
        .limit(5)
        .all()
    )

    return {
        "total_views": total_views,
        "unique_visitors": unique_visitors,
        "today_views": today_views,
        "week_views": week_views,
        "month_views": month_views,
        "top_books": [{"book_id": b, "views": v} for b, v in top_books],
    }


def get_book_analytics(session: Session, book_id: str, days: int = 30) -> dict:
    """Per-book analytics: daily views and top chapters."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    daily = (
        session.query(
            func.date(PageView.created_at).label("day"),
            func.count(PageView.id).label("views"),
        )
        .filter(PageView.book_id == book_id, PageView.created_at >= cutoff)
        .group_by(func.date(PageView.created_at))
        .order_by(func.date(PageView.created_at))
        .all()
    )

    top_chapters = (
        session.query(PageView.chapter_num, func.count(PageView.id).label("views"))
        .filter(
            PageView.book_id == book_id,
            PageView.chapter_num.isnot(None),
            PageView.created_at >= cutoff,
        )
        .group_by(PageView.chapter_num)
        .order_by(func.count(PageView.id).desc())
        .limit(10)
        .all()
    )

    total = (
        session.query(func.count(PageView.id))
        .filter(PageView.book_id == book_id, PageView.created_at >= cutoff)
        .scalar() or 0
    )

    return {
        "book_id": book_id,
        "days": days,
        "total_views": total,
        "daily": [{"date": str(d), "views": v} for d, v in daily],
        "top_chapters": [{"chapter_num": c, "views": v} for c, v in top_chapters],
    }


def get_top_books(session: Session, period: str = "week", limit: int = 20) -> list[dict]:
    """Top books by views within a time period."""
    cutoffs = {
        "day": timedelta(days=1),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
        "all": timedelta(days=36500),
    }
    delta = cutoffs.get(period, timedelta(days=7))
    since = datetime.utcnow() - delta

    rows = (
        session.query(PageView.book_id, func.count(PageView.id).label("views"))
        .filter(PageView.created_at >= since)
        .group_by(PageView.book_id)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
        .all()
    )

    return [{"book_id": b, "views": v} for b, v in rows]


def get_traffic(session: Session, days: int = 30) -> list[dict]:
    """Daily views + unique visitors for chart data."""
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        session.query(
            func.date(PageView.created_at).label("day"),
            func.count(PageView.id).label("views"),
            func.count(func.distinct(PageView.ip_hash)).label("visitors"),
        )
        .filter(PageView.created_at >= since)
        .group_by(func.date(PageView.created_at))
        .order_by(func.date(PageView.created_at))
        .all()
    )

    return [{"date": str(d), "views": v, "visitors": vis} for d, v, vis in rows]


def cleanup_old_views(session: Session, days: int = 90) -> int:
    """Delete page views older than N days. Returns count deleted."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    count = session.query(PageView).filter(PageView.created_at < cutoff).delete()
    session.commit()
    return count
