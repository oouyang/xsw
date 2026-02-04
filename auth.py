"""
Authentication module for admin panel.
Supports Google OAuth2 and password-based authentication with JWT tokens.
"""
import os
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from passlib.context import CryptContext
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Configuration
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
ADMIN_EMAIL_WHITELIST_STR = os.getenv("ADMIN_EMAIL_WHITELIST", "")
ADMIN_EMAIL_WHITELIST = [e.strip() for e in ADMIN_EMAIL_WHITELIST_STR.split(",") if e.strip()]

# Password hashing (using Argon2 for better security and compatibility)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Security scheme for FastAPI
# auto_error=False allows optional auth when AUTH_ENABLED=false
security = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """JWT token payload structure."""
    sub: str  # email
    auth_method: str
    exp: datetime
    iat: datetime


class AuthResponse(BaseModel):
    """Authentication response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


def verify_google_token(token: str) -> Dict[str, Any]:
    """
    Verify Google OAuth2 ID token and extract user info.

    Args:
        token: Google ID token from frontend

    Returns:
        dict with keys: email, google_id, name, picture

    Raises:
        ValueError: If token is invalid or email not whitelisted
    """
    if not GOOGLE_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID not configured")

    try:
        # Verify the token
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )

        # Extract user info
        email = idinfo.get('email')
        google_id = idinfo.get('sub')
        name = idinfo.get('name', '')
        picture = idinfo.get('picture', '')

        if not email:
            raise ValueError("Email not found in token")

        # Check email whitelist
        if ADMIN_EMAIL_WHITELIST and email not in ADMIN_EMAIL_WHITELIST:
            raise ValueError(f"Email {email} not authorized for admin access")

        return {
            'email': email,
            'google_id': google_id,
            'name': name,
            'picture': picture
        }
    except Exception as e:
        raise ValueError(f"Invalid Google token: {str(e)}")


def create_jwt_token(email: str, auth_method: str) -> tuple[str, datetime]:
    """
    Create a JWT token for authenticated user.

    Args:
        email: User email
        auth_method: 'google' or 'password'

    Returns:
        tuple of (token_string, expiration_datetime)
    """
    now = datetime.utcnow()
    expiration = now + timedelta(hours=JWT_EXPIRATION_HOURS)

    payload = {
        'sub': email,
        'auth_method': auth_method,
        'iat': now,
        'exp': expiration
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expiration


def decode_jwt_token(token: str) -> TokenPayload:
    """
    Decode and verify JWT token.

    Args:
        token: JWT token string

    Returns:
        TokenPayload with user info

    Raises:
        jwt.InvalidTokenError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise jwt.InvalidTokenError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f"Invalid token: {str(e)}")


async def require_admin_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> TokenPayload:
    """
    FastAPI dependency to require admin authentication.
    Use this to protect admin endpoints.

    Can be disabled via AUTH_ENABLED=false environment variable.

    Example:
        @app.get("/admin/stats")
        def get_stats(auth: TokenPayload = Depends(require_admin_auth)):
            # Auth verified, proceed
            pass
    """
    # Bypass authentication if AUTH_ENABLED is false
    if not AUTH_ENABLED:
        return TokenPayload(
            sub="admin@examp.com",
            auth_method="disabled",
            exp=datetime.utcnow() + timedelta(hours=24),
            iat=datetime.utcnow()
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token_payload = decode_jwt_token(credentials.credentials)
        return token_payload
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def init_admin_users(db_manager):
    """
    Initialize admin users table with default password admin if no users exist.
    Call this during application startup.
    Skips initialization if AUTH_ENABLED is false.
    """
    if not AUTH_ENABLED:
        print("[AUTH] Authentication disabled (AUTH_ENABLED=false), skipping admin user initialization")
        return

    from db_models import AdminUser

    session = db_manager.get_session()
    try:
        # Check if any admin users exist
        admin_count = session.query(AdminUser).count()

        if admin_count == 0:
            # Create default password admin
            default_admin = AdminUser(
                email="admin@example.com",
                auth_method="password",
                password_hash=hash_password("admin"),
                is_active=True
            )
            session.add(default_admin)
            session.commit()
            print("[AUTH] Created default admin user (admin@example.com / admin)")
            print("[AUTH] IMPORTANT: Change this password or disable password auth in production!")
    except Exception as e:
        print(f"[AUTH] Error initializing admin users: {e}")
        session.rollback()
    finally:
        session.close()
