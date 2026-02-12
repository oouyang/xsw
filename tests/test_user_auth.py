"""Tests for user authentication (user_auth.py)."""
import pytest
import jwt
from datetime import datetime, timedelta

import os

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("BASE_URL", "https://czbooks.net")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from user_auth import (
    create_user_jwt,
    decode_user_jwt,
    find_or_create_user,
    build_auth_response,
    JWT_SECRET,
    JWT_ALGORITHM,
)
from db_models import UserOAuth, init_database


@pytest.fixture
def db_session():
    """Create a fresh in-memory database for each test."""
    manager = init_database("sqlite:///:memory:")
    session = manager.get_session()
    yield session
    session.close()


class TestUserJWT:
    def test_create_user_jwt_returns_valid_token(self):
        token, expiration = create_user_jwt(42, "Test User")
        assert isinstance(token, str)
        assert expiration > datetime.utcnow()

    def test_decode_user_jwt_round_trip(self):
        token, _ = create_user_jwt(42, "Test User")
        payload = decode_user_jwt(token)
        assert payload.sub == 42
        assert payload.display_name == "Test User"
        assert payload.role == "user"

    def test_decode_user_jwt_rejects_admin_token(self):
        """User JWT decoder should reject tokens with role != 'user'."""
        payload = {
            "sub": "admin@example.com",
            "role": "admin",
            "auth_method": "password",
            "display_name": "Admin",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=24),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(jwt.InvalidTokenError, match="Not a user token"):
            decode_user_jwt(token)

    def test_decode_user_jwt_rejects_expired_token(self):
        payload = {
            "sub": 1,
            "display_name": "Expired User",
            "role": "user",
            "iat": datetime.utcnow() - timedelta(days=60),
            "exp": datetime.utcnow() - timedelta(days=1),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(jwt.InvalidTokenError, match="expired"):
            decode_user_jwt(token)

    def test_decode_user_jwt_rejects_garbage(self):
        with pytest.raises(jwt.InvalidTokenError):
            decode_user_jwt("not.a.jwt")


class TestFindOrCreateUser:
    def test_creates_new_user(self, db_session):
        user = find_or_create_user(
            db_session,
            provider="google",
            provider_user_id="g123",
            email="test@example.com",
            name="Test User",
            avatar="https://example.com/pic.jpg",
        )
        assert user.id is not None
        assert user.display_name == "Test User"
        assert user.email == "test@example.com"

        # Verify OAuth record was created
        oauth = db_session.query(UserOAuth).filter(UserOAuth.user_id == user.id).first()
        assert oauth is not None
        assert oauth.provider == "google"
        assert oauth.provider_user_id == "g123"

    def test_returns_existing_user_for_same_provider(self, db_session):
        user1 = find_or_create_user(
            db_session, "google", "g123", "test@example.com", "User 1", None
        )
        user2 = find_or_create_user(
            db_session, "google", "g123", "test@example.com", "User 1 Updated", None
        )
        assert user1.id == user2.id
        # Name should be updated
        assert user2.display_name == "User 1"  # display_name not changed (only provider_name)

    def test_merges_by_email(self, db_session):
        """If user signed in with Google, then later with Facebook using same email,
        both should link to the same User."""
        user1 = find_or_create_user(
            db_session, "google", "g123", "shared@example.com", "User", None
        )
        user2 = find_or_create_user(
            db_session, "facebook", "fb456", "shared@example.com", "User", None
        )
        assert user1.id == user2.id

        # Should have 2 OAuth links
        oauths = db_session.query(UserOAuth).filter(UserOAuth.user_id == user1.id).all()
        assert len(oauths) == 2
        providers = {o.provider for o in oauths}
        assert providers == {"google", "facebook"}

    def test_no_merge_without_email(self, db_session):
        """WeChat users (no email) should not merge with others."""
        user1 = find_or_create_user(
            db_session, "google", "g123", "test@example.com", "Google User", None
        )
        user2 = find_or_create_user(
            db_session, "wechat", "wx789", None, "WeChat User", None
        )
        assert user1.id != user2.id

    def test_stores_access_and_refresh_tokens(self, db_session):
        user = find_or_create_user(
            db_session,
            "wechat", "wx123", None, "WX User", None,
            access_token="at_123",
            refresh_token="rt_456",
        )
        oauth = db_session.query(UserOAuth).filter(UserOAuth.user_id == user.id).first()
        assert oauth.access_token == "at_123"
        assert oauth.refresh_token == "rt_456"


class TestBuildAuthResponse:
    def test_builds_response(self, db_session):
        user = find_or_create_user(
            db_session, "google", "g999", "resp@example.com", "Resp User", "https://pic.jpg"
        )
        resp = build_auth_response(user)
        assert resp.access_token
        assert resp.token_type == "bearer"
        assert resp.expires_in > 0
        assert resp.user.id == user.id
        assert resp.user.display_name == "Resp User"
        assert resp.user.email == "resp@example.com"
