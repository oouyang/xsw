# exception_middleware.py
"""
FastAPI middleware for catching unhandled exceptions and sending email notifications.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from datetime import datetime, timezone
import socket
import platform
import sys

logger = logging.getLogger("exception-middleware")


class ExceptionNotificationMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and sends email notifications."""

    def __init__(self, app, exception_notifier):
        super().__init__(app)
        self.exception_notifier = exception_notifier

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response

        except HTTPException:
            # FastAPI HTTPExceptions are intentional (400, 404, etc.)
            # Don't notify for these
            raise

        except RequestValidationError:
            # Pydantic validation errors (422) - client error, don't notify
            raise

        except Exception as exc:
            # Capture unhandled exception (500-level errors only)
            # Use logger.exception to preserve stack trace in logs
            logger.exception(
                f"[ExceptionMiddleware] Unhandled exception in {request.method} {request.url.path}"
            )

            # Build context
            context = self._build_context(request, exc)

            # Send notification (async)
            self.exception_notifier.notify(exc, context)

            # Return error response to client
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "message": "An unexpected error occurred. Administrators have been notified.",
                },
            )

    def _build_context(self, request: Request, exc: Exception) -> dict:
        """Extract request context for email."""
        # Extract user info from JWT if present
        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                import jwt

                token = auth_header.split(" ")[1]
                payload = jwt.decode(token, options={"verify_signature": False})
                user_id = payload.get("user_id") or payload.get("sub")
            except Exception:
                pass

        # Get client IP
        ip_address = request.client.host if request.client else "unknown"
        if "x-forwarded-for" in request.headers:
            ip_address = request.headers["x-forwarded-for"].split(",")[0].strip()

        # Sanitize headers - whitelist only safe headers
        # NEVER include: authorization, cookie, set-cookie, x-api-key
        safe_headers = {}
        ALLOWED_HEADERS = {
            "user-agent",
            "referer",
            "x-request-id",
            "x-forwarded-for",
            "x-real-ip",
            "cf-connecting-ip",
            "cf-ray",
            "content-type",
        }
        for key, value in request.headers.items():
            if key.lower() in ALLOWED_HEADERS:
                safe_headers[key] = value

        return {
            "endpoint": f"{request.method} {request.url.path}",
            "method": request.method,
            "user_id": user_id,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "headers": safe_headers,  # Whitelisted headers only
        }
