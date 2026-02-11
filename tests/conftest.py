"""Shared test fixtures for XSW backend tests."""
import os

# Set environment variables BEFORE importing the app
os.environ["AUTH_ENABLED"] = "false"
os.environ["DB_PATH"] = ":memory:"
os.environ["BASE_URL"] = "https://czbooks.net"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["CACHE_TTL_SECONDS"] = "900"

import pytest
from fastapi.testclient import TestClient

import main_optimized
from main_optimized import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FetchMock:
    """Mock replacement for main_optimized.fetch_html with URL registry."""

    def __init__(self):
        self.registry: dict[str, str] = {}
        self.call_log: list[str] = []

    def __call__(self, url: str) -> str:
        self.call_log.append(url)
        if url in self.registry:
            return self.registry[url]
        raise RuntimeError(f"Unmocked URL: {url}")

    def register(self, url: str, html: str) -> None:
        self.registry[url] = html


@pytest.fixture
def mock_fetch(monkeypatch):
    """Patch main_optimized.fetch_html with a FetchMock instance."""
    mock = FetchMock()
    monkeypatch.setattr(main_optimized, "fetch_html", mock)
    return mock


@pytest.fixture
def client(mock_fetch):
    """FastAPI TestClient with mocked fetch_html and fresh in-memory DB."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cache_mgr_fixture():
    """Standalone CacheManager with a fresh in-memory SQLite DB."""
    from db_models import init_database
    from cache_manager import CacheManager

    init_database("sqlite:///:memory:")
    mgr = CacheManager(ttl_seconds=900, max_memory_items=500)
    return mgr
