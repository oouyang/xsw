"""Tests for the analytics module and admin analytics endpoints."""
import os

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("ANALYTICS_DB_PATH", ":memory:")
os.environ.setdefault("BASE_URL", "https://czbooks.net")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("CACHE_TTL_SECONDS", "900")

import time
import queue
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import analytics
from analytics import PageView, hash_ip, hash_user_agent, log_page_view, _hash16
from main_optimized import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fresh_analytics_db():
    """Give every test a fresh in-memory analytics DB and drain the queue."""
    analytics.init_db("sqlite:///:memory:")
    # Drain any leftover items from previous tests
    while not analytics._queue.empty():
        try:
            analytics._queue.get_nowait()
        except queue.Empty:
            break
    yield


@pytest.fixture
def session(_fresh_analytics_db):
    s = analytics.get_session()
    yield s
    s.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Unit tests: hashing
# ---------------------------------------------------------------------------

def test_hash_ip_deterministic():
    assert hash_ip("127.0.0.1") == hash_ip("127.0.0.1")


def test_hash_ip_length():
    assert len(hash_ip("192.168.1.1")) == 16


def test_hash_user_agent_differs_from_ip():
    # Same input, same output — function is just sha256 truncated
    assert hash_user_agent("test") == _hash16("test")


def test_different_inputs_different_hashes():
    assert hash_ip("1.2.3.4") != hash_ip("5.6.7.8")


# ---------------------------------------------------------------------------
# Unit tests: queue / log_page_view
# ---------------------------------------------------------------------------

def test_log_page_view_enqueues():
    log_page_view(book_id="abc", chapter_num=1, ip="1.2.3.4")
    item = analytics._queue.get_nowait()
    assert item["book_id"] == "abc"
    assert item["chapter_num"] == 1
    assert item["ip_hash"] == hash_ip("1.2.3.4")
    assert isinstance(item["created_at"], datetime)


def test_log_page_view_drops_when_full():
    """When queue is full, log_page_view should not raise."""
    original_queue = analytics._queue
    analytics._queue = queue.Queue(maxsize=1)
    try:
        log_page_view(book_id="a", chapter_num=1)
        # Queue is now full
        log_page_view(book_id="b", chapter_num=2)  # should not raise
        # Only first item should be in queue
        item = analytics._queue.get_nowait()
        assert item["book_id"] == "a"
        assert analytics._queue.empty()
    finally:
        analytics._queue = original_queue


# ---------------------------------------------------------------------------
# Unit tests: flush / batch insert
# ---------------------------------------------------------------------------

def test_flush_inserts_records(session):
    records = [
        {
            "book_id": f"book{i}",
            "chapter_num": i,
            "user_id": None,
            "ip_hash": hash_ip("1.2.3.4"),
            "user_agent_hash": None,
            "referer": None,
            "created_at": datetime.utcnow(),
        }
        for i in range(5)
    ]
    analytics._flush(records)
    count = session.query(PageView).count()
    assert count == 5


# ---------------------------------------------------------------------------
# Unit tests: query helpers
# ---------------------------------------------------------------------------

def test_get_summary_empty(session):
    result = analytics.get_summary(session)
    assert result["total_views"] == 0
    assert result["unique_visitors"] == 0
    assert result["today_views"] == 0
    assert result["top_books"] == []


def test_get_summary_with_data(session):
    now = datetime.utcnow()
    for i in range(3):
        session.add(PageView(
            book_id="book1", chapter_num=i + 1,
            ip_hash=f"hash{i}", created_at=now,
        ))
    session.add(PageView(
        book_id="book2", chapter_num=1,
        ip_hash="hashX", created_at=now,
    ))
    session.commit()

    result = analytics.get_summary(session)
    assert result["total_views"] == 4
    assert result["unique_visitors"] == 4
    assert result["today_views"] == 4
    assert len(result["top_books"]) == 2
    assert result["top_books"][0]["book_id"] == "book1"
    assert result["top_books"][0]["views"] == 3


def test_get_book_analytics(session):
    now = datetime.utcnow()
    for i in range(5):
        session.add(PageView(
            book_id="bookA", chapter_num=1,
            ip_hash="h1", created_at=now,
        ))
    session.add(PageView(
        book_id="bookA", chapter_num=2,
        ip_hash="h2", created_at=now,
    ))
    session.commit()

    result = analytics.get_book_analytics(session, "bookA", days=30)
    assert result["book_id"] == "bookA"
    assert result["total_views"] == 6
    assert len(result["top_chapters"]) == 2
    assert result["top_chapters"][0]["chapter_num"] == 1
    assert result["top_chapters"][0]["views"] == 5


def test_get_top_books_period_filter(session):
    now = datetime.utcnow()
    old = now - timedelta(days=10)

    session.add(PageView(book_id="recent", chapter_num=1, ip_hash="h1", created_at=now))
    session.add(PageView(book_id="old", chapter_num=1, ip_hash="h2", created_at=old))
    session.commit()

    # "day" period should only include recent
    result = analytics.get_top_books(session, period="day", limit=10)
    book_ids = [r["book_id"] for r in result]
    assert "recent" in book_ids
    assert "old" not in book_ids


def test_get_traffic(session):
    now = datetime.utcnow()
    session.add(PageView(book_id="b1", chapter_num=1, ip_hash="h1", created_at=now))
    session.add(PageView(book_id="b1", chapter_num=2, ip_hash="h1", created_at=now))
    session.add(PageView(book_id="b1", chapter_num=3, ip_hash="h2", created_at=now))
    session.commit()

    result = analytics.get_traffic(session, days=1)
    assert len(result) == 1
    assert result[0]["views"] == 3
    assert result[0]["visitors"] == 2


def test_cleanup_old_views(session):
    now = datetime.utcnow()
    old = now - timedelta(days=100)
    session.add(PageView(book_id="b1", chapter_num=1, ip_hash="h1", created_at=now))
    session.add(PageView(book_id="b2", chapter_num=1, ip_hash="h2", created_at=old))
    session.commit()

    deleted = analytics.cleanup_old_views(session, days=90)
    assert deleted == 1
    assert session.query(PageView).count() == 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_admin_analytics_summary_endpoint(client):
    resp = client.get("/xsw/api/admin/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_views" in data
    assert "top_books" in data


def test_admin_analytics_top_endpoint(client):
    resp = client.get("/xsw/api/admin/analytics/top?period=week&limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_admin_analytics_traffic_endpoint(client):
    resp = client.get("/xsw/api/admin/analytics/traffic?days=7")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_admin_analytics_cleanup_endpoint(client):
    resp = client.post("/xsw/api/admin/analytics/cleanup?days=90")
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted" in data
    assert data["older_than_days"] == 90
