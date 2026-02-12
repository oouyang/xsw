"""
User authentication module for regular readers.
Supports Google, Facebook, Apple, and WeChat OAuth.
Separate from admin auth (auth.py).
"""
import os
import jwt
import requests
import threading
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db_models import User, UserOAuth

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
USER_JWT_EXPIRATION_DAYS = int(os.getenv("USER_JWT_EXPIRATION_DAYS", "30"))

# OAuth provider credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
FACEBOOK_APP_ID = os.getenv("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY = os.getenv("APPLE_PRIVATE_KEY", "")
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "")

# Security scheme (auto_error=False for optional auth)
user_security = HTTPBearer(auto_error=False)

# Apple public keys cache
_apple_keys_cache = {"keys": None, "fetched_at": None}
_apple_keys_lock = threading.Lock()
APPLE_KEYS_TTL = 3600  # 1 hour


class UserTokenPayload(BaseModel):
    """User JWT token payload."""
    sub: int  # user_id
    display_name: str
    role: str  # "user"
    exp: datetime
    iat: datetime


class UserProfile(BaseModel):
    """User profile response."""
    id: int
    display_name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class UserAuthResponse(BaseModel):
    """User authentication response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


# -----------------------
# JWT Functions
# -----------------------
def create_user_jwt(user_id: int, display_name: str) -> tuple[str, datetime]:
    """Create a JWT token for a regular user (30-day expiration)."""
    now = datetime.utcnow()
    expiration = now + timedelta(days=USER_JWT_EXPIRATION_DAYS)

    payload = {
        "sub": str(user_id),
        "display_name": display_name,
        "role": "user",
        "iat": now,
        "exp": expiration,
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expiration


def decode_user_jwt(token: str) -> UserTokenPayload:
    """Decode and verify a user JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") != "user":
            raise jwt.InvalidTokenError("Not a user token")
        payload["sub"] = int(payload["sub"])
        return UserTokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise jwt.InvalidTokenError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f"Invalid token: {str(e)}")


# -----------------------
# FastAPI Dependencies
# -----------------------
async def require_user_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(user_security),
) -> UserTokenPayload:
    """FastAPI dependency that requires a valid user JWT."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return decode_user_jwt(credentials.credentials)
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def optional_user_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(user_security),
) -> Optional[UserTokenPayload]:
    """FastAPI dependency that returns user if token present, None otherwise."""
    if not credentials:
        return None

    try:
        return decode_user_jwt(credentials.credentials)
    except jwt.InvalidTokenError:
        return None


# -----------------------
# Account Merging
# -----------------------
def find_or_create_user(
    db: Session,
    provider: str,
    provider_user_id: str,
    email: Optional[str],
    name: str,
    avatar: Optional[str],
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> User:
    """
    Find existing user or create new one. Implements account merging:
    1. Look up (provider, provider_user_id) -> login existing user
    2. If not found and email non-null, find UserOAuth with matching email -> link
    3. If no match, create new User + UserOAuth
    """
    now = datetime.utcnow()

    # Step 1: Check for existing OAuth link
    oauth = (
        db.query(UserOAuth)
        .filter(
            UserOAuth.provider == provider,
            UserOAuth.provider_user_id == provider_user_id,
        )
        .first()
    )

    if oauth:
        # Existing user — update metadata
        oauth.last_used_at = now
        oauth.provider_name = name or oauth.provider_name
        oauth.provider_avatar = avatar or oauth.provider_avatar
        if email:
            oauth.provider_email = email
        if access_token:
            oauth.access_token = access_token
        if refresh_token:
            oauth.refresh_token = refresh_token

        user = oauth.user
        user.last_login_at = now
        if avatar and not user.avatar_url:
            user.avatar_url = avatar
        db.commit()
        return user

    # Step 2: Try to match by email
    user = None
    if email:
        existing_oauth = (
            db.query(UserOAuth)
            .filter(UserOAuth.provider_email == email)
            .first()
        )
        if existing_oauth:
            user = existing_oauth.user

    # Step 3: Create new user if no match
    if not user:
        user = User(
            display_name=name or "Reader",
            email=email,
            avatar_url=avatar,
            is_active=True,
            created_at=now,
            last_login_at=now,
        )
        db.add(user)
        db.flush()  # Get the user.id

    # Create new OAuth link
    new_oauth = UserOAuth(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        provider_email=email,
        provider_name=name,
        provider_avatar=avatar,
        access_token=access_token,
        refresh_token=refresh_token,
        created_at=now,
        last_used_at=now,
    )
    db.add(new_oauth)

    user.last_login_at = now
    db.commit()
    return user


# -----------------------
# OAuth Verification
# -----------------------
def verify_google_user(id_token_str: str) -> dict:
    """
    Verify Google ID token for regular user login.
    Unlike admin auth, no email whitelist check.
    """
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests

    if not GOOGLE_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID not configured")

    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
        return {
            "provider_user_id": idinfo.get("sub"),
            "email": idinfo.get("email"),
            "name": idinfo.get("name", ""),
            "avatar": idinfo.get("picture", ""),
        }
    except Exception as e:
        raise ValueError(f"Invalid Google token: {str(e)}")


def verify_facebook_user(access_token: str) -> dict:
    """Verify Facebook access token by calling Graph API."""
    if not FACEBOOK_APP_ID:
        raise ValueError("FACEBOOK_APP_ID not configured")

    try:
        resp = requests.get(
            "https://graph.facebook.com/me",
            params={
                "fields": "id,name,email,picture.type(large)",
                "access_token": access_token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise ValueError(data["error"].get("message", "Facebook API error"))

        return {
            "provider_user_id": data["id"],
            "email": data.get("email"),
            "name": data.get("name", ""),
            "avatar": data.get("picture", {}).get("data", {}).get("url", ""),
        }
    except requests.RequestException as e:
        raise ValueError(f"Failed to verify Facebook token: {str(e)}")


def _fetch_apple_public_keys() -> list:
    """Fetch and cache Apple's public keys for JWT verification."""
    with _apple_keys_lock:
        now = datetime.utcnow()
        if (
            _apple_keys_cache["keys"]
            and _apple_keys_cache["fetched_at"]
            and (now - _apple_keys_cache["fetched_at"]).total_seconds() < APPLE_KEYS_TTL
        ):
            return _apple_keys_cache["keys"]

        try:
            resp = requests.get(
                "https://appleid.apple.com/auth/keys",
                timeout=10,
            )
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
            _apple_keys_cache["keys"] = keys
            _apple_keys_cache["fetched_at"] = now
            return keys
        except requests.RequestException as e:
            if _apple_keys_cache["keys"]:
                return _apple_keys_cache["keys"]
            raise ValueError(f"Failed to fetch Apple public keys: {str(e)}")


def verify_apple_user(id_token_str: str) -> dict:
    """Verify Apple ID token using Apple's public keys."""
    if not APPLE_CLIENT_ID:
        raise ValueError("APPLE_CLIENT_ID not configured")

    try:
        # Decode header to find the key ID
        header = jwt.get_unverified_header(id_token_str)
        kid = header.get("kid")

        # Fetch Apple's public keys
        apple_keys = _fetch_apple_public_keys()

        # Find the matching key
        matching_key = None
        for key in apple_keys:
            if key.get("kid") == kid:
                matching_key = key
                break

        if not matching_key:
            raise ValueError("No matching Apple public key found")

        # Construct public key and verify
        from jwt.algorithms import RSAAlgorithm

        public_key = RSAAlgorithm.from_jwk(matching_key)

        payload = jwt.decode(
            id_token_str,
            public_key,
            algorithms=["RS256"],
            audience=APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com",
        )

        return {
            "provider_user_id": payload.get("sub"),
            "email": payload.get("email"),
            "name": "",  # Apple only sends name on first login via authorization_code
            "avatar": None,
        }
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid Apple token: {str(e)}")
    except Exception as e:
        raise ValueError(f"Apple verification failed: {str(e)}")


def verify_wechat_user(code: str) -> dict:
    """
    Exchange WeChat auth code for access_token, then fetch user info.
    """
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise ValueError("WECHAT_APP_ID or WECHAT_APP_SECRET not configured")

    try:
        # Step 1: Exchange code for access_token
        token_resp = requests.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": WECHAT_APP_ID,
                "secret": WECHAT_APP_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_data = token_resp.json()

        if "errcode" in token_data:
            raise ValueError(
                f"WeChat token exchange failed: {token_data.get('errmsg', 'Unknown error')}"
            )

        access_token = token_data["access_token"]
        openid = token_data["openid"]
        refresh_token = token_data.get("refresh_token")

        # Step 2: Fetch user info
        info_resp = requests.get(
            "https://api.weixin.qq.com/sns/userinfo",
            params={
                "access_token": access_token,
                "openid": openid,
                "lang": "zh_TW",
            },
            timeout=10,
        )
        info_data = info_resp.json()

        if "errcode" in info_data:
            raise ValueError(
                f"WeChat user info failed: {info_data.get('errmsg', 'Unknown error')}"
            )

        return {
            "provider_user_id": openid,
            "email": None,  # WeChat doesn't provide email
            "name": info_data.get("nickname", ""),
            "avatar": info_data.get("headimgurl", ""),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
    except requests.RequestException as e:
        raise ValueError(f"WeChat verification failed: {str(e)}")


# -----------------------
# Helper to build auth response
# -----------------------
def build_auth_response(user: User) -> UserAuthResponse:
    """Build a UserAuthResponse from a User model."""
    token, expiration = create_user_jwt(user.id, user.display_name)
    expires_in = int((expiration - datetime.utcnow()).total_seconds())

    return UserAuthResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserProfile(
            id=user.id,
            display_name=user.display_name,
            email=user.email,
            avatar_url=user.avatar_url,
        ),
    )
