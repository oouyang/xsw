"""Tests for comment API endpoints."""
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


def _create_test_user(name="Test Reader", email="reader@example.com") -> tuple[int, str]:
    import db_models as _db

    session = _db.db_manager.get_session()
    try:
        user = User(display_name=name, email=email, is_active=True)
        session.add(user)
        session.commit()
        session.refresh(user)
        token, _ = create_user_jwt(user.id, user.display_name)
        return user.id, token
    finally:
        session.close()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestCommentCRUD:
    def test_create_comment(self, client):
        _, token = _create_test_user()

        resp = client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "Great novel!"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["text"] == "Great novel!"
        assert data["book_id"] == "book1"
        assert data["display_name"] == "Test Reader"
        assert data["id"] > 0

    def test_list_comments(self, client):
        _, token = _create_test_user()

        # Create two comments
        client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "First comment"},
            headers=_auth_header(token),
        )
        client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "Second comment"},
            headers=_auth_header(token),
        )

        # List (no auth required)
        resp = client.get(f"{BASE}/books/book1/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Newest first
        assert data[0]["text"] == "Second comment"
        assert data[1]["text"] == "First comment"

    def test_list_comments_empty(self, client):
        resp = client.get(f"{BASE}/books/nocomments/comments")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_delete_own_comment(self, client):
        _, token = _create_test_user()

        # Create
        create_resp = client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "To be deleted"},
            headers=_auth_header(token),
        )
        comment_id = create_resp.json()["id"]

        # Delete
        resp = client.delete(
            f"{BASE}/user/comments/{comment_id}",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify gone
        list_resp = client.get(f"{BASE}/books/book1/comments")
        assert len(list_resp.json()) == 0

    def test_delete_not_found(self, client):
        _, token = _create_test_user()

        resp = client.delete(
            f"{BASE}/user/comments/99999",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404


class TestCommentAuth:
    def test_create_requires_auth(self, client):
        resp = client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "No auth"},
        )
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        resp = client.delete(f"{BASE}/user/comments/1")
        assert resp.status_code == 401

    def test_cannot_delete_others_comment(self, client):
        user1_id, token1 = _create_test_user("User1", "u1@example.com")

        # User 1 creates comment
        create_resp = client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "User 1 comment"},
            headers=_auth_header(token1),
        )
        comment_id = create_resp.json()["id"]

        # User 2 tries to delete
        import db_models as _db

        session = _db.db_manager.get_session()
        user2 = User(display_name="User2", email="u2@example.com", is_active=True)
        session.add(user2)
        session.commit()
        session.refresh(user2)
        token2, _ = create_user_jwt(user2.id, user2.display_name)
        session.close()

        resp = client.delete(
            f"{BASE}/user/comments/{comment_id}",
            headers=_auth_header(token2),
        )
        assert resp.status_code == 403


class TestCommentValidation:
    def test_empty_text_rejected(self, client):
        _, token = _create_test_user()

        resp = client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "   "},
            headers=_auth_header(token),
        )
        assert resp.status_code == 400

    def test_too_long_text_rejected(self, client):
        _, token = _create_test_user()

        resp = client.post(
            f"{BASE}/books/book1/comments",
            json={"text": "x" * 1001},
            headers=_auth_header(token),
        )
        assert resp.status_code == 400
