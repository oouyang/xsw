"""Tests for reading progress API endpoints."""
import os

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("BASE_URL", "https://czbooks.net")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from user_auth import create_user_jwt
from db_models import User

import main_optimized
from main_optimized import app

BASE = "/xsw/api"


class FetchMock:
    """Mock replacement for main_optimized.fetch_html."""

    def __init__(self):
        self.registry: dict[str, str] = {}

    def __call__(self, url: str) -> str:
        if url in self.registry:
            return self.registry[url]
        raise RuntimeError(f"Unmocked URL: {url}")

    def register(self, url: str, html: str) -> None:
        self.registry[url] = html


@pytest.fixture
def mock_fetch(monkeypatch):
    mock = FetchMock()
    monkeypatch.setattr(main_optimized, "fetch_html", mock)
    return mock


@pytest.fixture
def client(mock_fetch):
    with TestClient(app) as c:
        yield c


def _create_test_user() -> tuple[int, str]:
    """Create a test user in the DB and return (user_id, jwt_token)."""
    import db_models as _db

    session = _db.db_manager.get_session()
    try:
        user = User(
            display_name="Test Reader",
            email="reader@example.com",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        token, _ = create_user_jwt(user.id, user.display_name)
        return user.id, token
    finally:
        session.close()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestProgressCRUD:
    def test_upsert_progress(self, client):
        user_id, token = _create_test_user()

        resp = client.put(
            f"{BASE}/user/progress/book123",
            json={
                "chapter_number": 42,
                "chapter_title": "Chapter 42",
                "chapter_id": "ch42",
                "book_name": "Test Novel",
            },
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["book_id"] == "book123"
        assert data["chapter_number"] == 42
        assert data["chapter_title"] == "Chapter 42"
        assert data["book_name"] == "Test Novel"

    def test_get_progress(self, client):
        user_id, token = _create_test_user()

        # Create progress first
        client.put(
            f"{BASE}/user/progress/book123",
            json={"chapter_number": 10, "chapter_title": "Ch 10", "book_name": "Novel"},
            headers=_auth_header(token),
        )

        resp = client.get(
            f"{BASE}/user/progress/book123",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter_number"] == 10

    def test_get_progress_not_found(self, client):
        _, token = _create_test_user()

        resp = client.get(
            f"{BASE}/user/progress/nonexistent",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404

    def test_list_progress(self, client):
        _, token = _create_test_user()

        # Create progress for two books
        client.put(
            f"{BASE}/user/progress/book1",
            json={"chapter_number": 5, "book_name": "Book One"},
            headers=_auth_header(token),
        )
        client.put(
            f"{BASE}/user/progress/book2",
            json={"chapter_number": 15, "book_name": "Book Two"},
            headers=_auth_header(token),
        )

        resp = client.get(
            f"{BASE}/user/progress",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Should be sorted by updated_at DESC (book2 most recent)
        assert data[0]["book_id"] == "book2"
        assert data[1]["book_id"] == "book1"

    def test_upsert_updates_existing(self, client):
        _, token = _create_test_user()

        # Create
        client.put(
            f"{BASE}/user/progress/book1",
            json={"chapter_number": 5, "book_name": "Novel"},
            headers=_auth_header(token),
        )

        # Update
        resp = client.put(
            f"{BASE}/user/progress/book1",
            json={"chapter_number": 20, "chapter_title": "Ch 20", "book_name": "Novel"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["chapter_number"] == 20

        # Verify only one record exists
        list_resp = client.get(
            f"{BASE}/user/progress",
            headers=_auth_header(token),
        )
        assert len(list_resp.json()) == 1

    def test_delete_progress(self, client):
        _, token = _create_test_user()

        # Create
        client.put(
            f"{BASE}/user/progress/book1",
            json={"chapter_number": 5, "book_name": "Novel"},
            headers=_auth_header(token),
        )

        # Delete
        resp = client.delete(
            f"{BASE}/user/progress/book1",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify it's gone
        get_resp = client.get(
            f"{BASE}/user/progress/book1",
            headers=_auth_header(token),
        )
        assert get_resp.status_code == 404

    def test_delete_progress_not_found(self, client):
        _, token = _create_test_user()

        resp = client.delete(
            f"{BASE}/user/progress/nonexistent",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404


class TestProgressAuth:
    def test_requires_auth(self, client):
        """All progress endpoints require user auth."""
        resp = client.get(f"{BASE}/user/progress")
        assert resp.status_code == 401

        resp = client.get(f"{BASE}/user/progress/book1")
        assert resp.status_code == 401

        resp = client.put(
            f"{BASE}/user/progress/book1",
            json={"chapter_number": 1},
        )
        assert resp.status_code == 401

        resp = client.delete(f"{BASE}/user/progress/book1")
        assert resp.status_code == 401

    def test_rejects_invalid_token(self, client):
        resp = client.get(
            f"{BASE}/user/progress",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_user_isolation(self, client):
        """Users should only see their own progress."""
        # Create two users
        user1_id, token1 = _create_test_user()

        import db_models as _db

        session = _db.db_manager.get_session()
        user2 = User(display_name="User Two", email="user2@example.com", is_active=True)
        session.add(user2)
        session.commit()
        session.refresh(user2)
        token2, _ = create_user_jwt(user2.id, user2.display_name)
        session.close()

        # User 1 saves progress
        client.put(
            f"{BASE}/user/progress/book1",
            json={"chapter_number": 10, "book_name": "User 1 Book"},
            headers=_auth_header(token1),
        )

        # User 2 should see empty progress
        resp = client.get(
            f"{BASE}/user/progress",
            headers=_auth_header(token2),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestUserAuthEndpoints:
    def test_verify_valid_token(self, client):
        _, token = _create_test_user()
        resp = client.get(
            f"{BASE}/user/auth/verify",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_get_profile(self, client):
        user_id, token = _create_test_user()
        resp = client.get(
            f"{BASE}/user/auth/me",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == user_id
        assert data["display_name"] == "Test Reader"
        assert data["email"] == "reader@example.com"
