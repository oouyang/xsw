# exception_notifier.py
"""
Exception email notification system with intelligent throttling.
Sends detailed exception reports to administrators via email.
"""

import logging
import hashlib
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from email_sender import EmailSender

logger = logging.getLogger("exception-notifier")


class ExceptionThrottler:
    """Throttles exception notifications using DB + memory cache."""

    def __init__(self, session_factory=None):
        # Allow injection of custom session factory for testing
        self.session_factory = session_factory
        # hash -> (last_sent, count, cached_at)
        self.cache: Dict[str, tuple[datetime, int, datetime]] = {}
        self.cache_lock = threading.Lock()
        self._cache_ttl = timedelta(minutes=5)

    def _get_session(self):
        """Get database session (injectable for testing)."""
        if self.session_factory:
            return self.session_factory()
        from db_models import db_manager

        return db_manager.get_session()

    def should_send(
        self, exception_hash: str, exc_type: str, endpoint: str
    ) -> tuple[bool, int]:
        """Returns (should_send, occurrence_count).

        CRITICAL: Uses BEGIN IMMEDIATE for SQLite to serialize write transactions.
        This prevents race conditions where two threads both decide to send email.
        """
        # Clean expired cache entries
        self._cleanup_cache()

        # Check cache first (fast path - negative caching for cooldown only)
        # Note: Sentinel values always miss cooldown check, falling through to DB for count increment.
        # This ensures every occurrence is recorded in DB count, which is critical for accurate throttling.
        with self.cache_lock:
            if exception_hash in self.cache:
                last_sent, count, cached_at = self.cache[exception_hash]
                # Cache hit - check if still valid
                if datetime.now(timezone.utc) - cached_at < self._cache_ttl:
                    if self._is_within_cooldown(last_sent, count):
                        return False, count

        # Query database with retry logic for SQLite lock contention
        from db_models import ExceptionLog
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError, OperationalError

        max_retries = 3
        retry_delay = 0.1  # 100ms

        for attempt in range(max_retries):
            session = self._get_session()
            try:
                # CRITICAL: Use BEGIN IMMEDIATE to acquire write lock immediately
                # This serializes all write transactions at DB level (SQLite-specific)
                session.execute(text("BEGIN IMMEDIATE"))

                log = (
                    session.query(ExceptionLog)
                    .filter_by(exception_hash=exception_hash)
                    .first()
                )

                now = datetime.now(timezone.utc)

                if not log:
                    # First occurrence - create new record
                    # CRITICAL: Use sentinel for last_sent_at (far past) since email hasn't been sent yet
                    # Will be updated to real timestamp by mark_sent() after email succeeds
                    sentinel = datetime(1970, 1, 1, tzinfo=timezone.utc)
                    log = ExceptionLog(
                        exception_hash=exception_hash,
                        exception_type=exc_type,
                        endpoint=endpoint,
                        count=1,
                        last_sent_at=sentinel,  # Sentinel - not actually sent yet
                        last_occurrence_at=now,
                    )
                    session.add(log)
                    session.commit()

                    with self.cache_lock:
                        self.cache[exception_hash] = (sentinel, 1, now)

                    return True, 1

                # Existing record - increment count
                log.count += 1
                log.last_occurrence_at = now

                # Decide whether to send BEFORE commit
                should_send = not self._is_within_cooldown(log.last_sent_at, log.count)

                # CRITICAL: Only commit count increment now
                # Do NOT update last_sent_at yet - that happens after email succeeds
                session.commit()

                # Update cache with current state
                with self.cache_lock:
                    self.cache[exception_hash] = (log.last_sent_at, log.count, now)

                # Break out of retry loop on success
                return should_send, log.count

            except IntegrityError:
                # Another thread created the record simultaneously
                # Roll back and retry query (record should exist now)
                session.rollback()
                if attempt < max_retries - 1:
                    import time

                    time.sleep(0)  # Yield to other thread
                    continue
                else:
                    raise

            except OperationalError as e:
                session.rollback()

                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    # SQLite contention - retry with exponential backoff
                    import time

                    time.sleep(retry_delay)
                    retry_delay *= 2
                    logger.debug(
                        f"[ExceptionThrottler] DB locked, retry {attempt + 1}/{max_retries}"
                    )
                    continue
                else:
                    # Real error or max retries exceeded
                    logger.error(f"[ExceptionThrottler] OperationalError: {e}")
                    raise

            except Exception as e:
                # Unexpected error
                session.rollback()
                logger.error(f"[ExceptionThrottler] Unexpected DB error: {e}")
                raise
            finally:
                # Close session each attempt (fresh session per retry)
                session.close()

    def mark_sent(self, exception_hash: str) -> bool:
        """Mark that email was successfully sent. Call this AFTER email succeeds.

        This updates last_sent_at in DB to reflect successful send.
        If not called, the exception remains eligible for immediate re-send.

        Returns:
            True if DB update succeeded, False otherwise
        """
        from db_models import ExceptionLog
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError

        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            session = self._get_session()
            try:
                # Use BEGIN IMMEDIATE for write serialization
                session.execute(text("BEGIN IMMEDIATE"))

                log = (
                    session.query(ExceptionLog)
                    .filter_by(exception_hash=exception_hash)
                    .first()
                )

                if log:
                    now = datetime.now(timezone.utc)
                    log.last_sent_at = now
                    session.commit()

                    # Update cache
                    with self.cache_lock:
                        # Preserve count from cache if exists
                        if exception_hash in self.cache:
                            _, count, _ = self.cache[exception_hash]
                            self.cache[exception_hash] = (now, count, now)

                    return True  # Success
                else:
                    # Log doesn't exist (shouldn't happen, but email already sent successfully)
                    # Return True to release inflight and avoid blocking future occurrences
                    logger.warning(
                        f"[ExceptionThrottler] mark_sent: log not found for {exception_hash}, but email sent"
                    )
                    return True

            except OperationalError as e:
                session.rollback()
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    import time

                    time.sleep(retry_delay)
                    retry_delay *= 2
                    logger.debug(
                        f"[ExceptionThrottler] mark_sent DB locked, retry {attempt + 1}/{max_retries}"
                    )
                    continue
                else:
                    logger.error(f"[ExceptionThrottler] Failed to mark_sent: {e}")
                    return False

            except Exception as e:
                session.rollback()
                logger.error(f"[ExceptionThrottler] Failed to mark_sent: {e}")
                return False

            finally:
                session.close()

        # Max retries exhausted
        return False

    def _is_within_cooldown(self, last_sent: datetime, count: int) -> bool:
        """Check if we're still in cooldown period.

        Note: Uses NEW count (after increment), so hitting the 4th occurrence
        immediately switches to 6h cooldown even if 1h hasn't passed yet.
        This is intentional to suppress spam faster.
        """
        if count <= 3:
            cooldown = timedelta(hours=1)
        elif count <= 10:
            cooldown = timedelta(hours=6)
        else:
            cooldown = timedelta(hours=24)

        return datetime.now(timezone.utc) - last_sent < cooldown

    def _cleanup_cache(self):
        """Remove expired cache entries (older than TTL)."""
        with self.cache_lock:
            now = datetime.now(timezone.utc)
            expired = [
                h
                for h, (_, _, cached_at) in self.cache.items()
                if now - cached_at >= self._cache_ttl
            ]
            for h in expired:
                del self.cache[h]


class ExceptionEmailFormatter:
    """Formats exception details as HTML email."""

    @staticmethod
    def format_email(
        exc: Exception,
        exc_traceback: str,
        context: Dict[str, Any],
        occurrence_count: int,
    ) -> tuple[str, str]:
        """Returns (subject, html_body)."""
        import html

        exc_type = type(exc).__name__
        endpoint = context.get("endpoint", "unknown")

        # Build subject line
        subject = f"[XSW Exception] {exc_type} in {endpoint}"
        if occurrence_count > 1:
            subject += f" ({occurrence_count}x)"

        # SECURITY: Remove CRLF to prevent email header injection
        subject = subject.replace("\r", "").replace("\n", " ")

        # Limit subject length to prevent overly long email headers
        subject = subject[:200]

        # SECURITY: Escape all user-controlled content for HTML
        exc_message = html.escape(str(exc))
        exc_traceback_safe = html.escape(exc_traceback)
        endpoint_safe = html.escape(context.get("endpoint", "N/A"))

        # Build HTML body
        badge = ""
        if occurrence_count > 1:
            badge = f'<span style="background:#ff6b6b;color:white;padding:4px 8px;border-radius:4px;font-size:12px;">Occurred {occurrence_count} times</span>'

        # Build headers section (outside f-string to avoid Python 3.11 escape issues)
        headers_section = ""
        if context.get("headers"):
            headers_lines = "\n".join(
                f"{html.escape(k)}: {html.escape(v)}"
                for k, v in context.get("headers", {}).items()
            )
            headers_section = f'<div class="section"><h2>📋 Headers (Sanitized)</h2><pre class="code">{headers_lines}</pre></div>'

        html_body = f"""
<html>
<head>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
.header {{ background: #e74c3c; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
.header h1 {{ margin: 0; font-size: 24px; }}
.section {{ padding: 20px; background: #f9f9f9; margin: 10px 0; border-radius: 4px; }}
.section h2 {{ margin-top: 0; color: #2c3e50; font-size: 18px; }}
.code {{ background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 4px; overflow-x: auto; font-family: 'Consolas', monospace; font-size: 13px; white-space: pre-wrap; word-wrap: break-word; }}
.info-grid {{ display: grid; grid-template-columns: 150px 1fr; gap: 10px; }}
.info-label {{ font-weight: bold; color: #555; }}
</style>
</head>
<body>
<div class="header">
<h1>⚠️ Exception Alert</h1>
<p style="margin: 5px 0 0 0;">{exc_type}: {exc_message}</p>
{badge}
</div>

<div class="section">
<h2>🎯 Request Context</h2>
<div class="info-grid">
<span class="info-label">Endpoint:</span><span>{endpoint_safe}</span>
<span class="info-label">Method:</span><span>{html.escape(context.get("method", "N/A"))}</span>
<span class="info-label">User ID:</span><span>{html.escape(str(context.get("user_id", "Anonymous")))}</span>
<span class="info-label">IP Address:</span><span>{html.escape(context.get("ip_address", "N/A"))}</span>
<span class="info-label">Timestamp:</span><span>{html.escape(context.get("timestamp", "N/A"))}</span>
</div>
</div>

{headers_section}

<div class="section">
<h2>🔍 Traceback</h2>
<pre class="code">{exc_traceback_safe}</pre>
</div>

<div class="section">
<h2>💻 Server Info</h2>
<div class="info-grid">
<span class="info-label">Hostname:</span><span>{html.escape(context.get("hostname", "N/A"))}</span>
<span class="info-label">Python:</span><span>{html.escape(context.get("python_version", "N/A"))}</span>
<span class="info-label">Platform:</span><span>{html.escape(context.get("platform", "N/A"))}</span>
</div>
</div>
</body>
</html>
"""
        return subject, html_body


class ExceptionNotifier:
    """Main exception notification orchestrator."""

    def __init__(
        self, email_sender: EmailSender, recipient_email: str, session_factory=None
    ):
        self.email_sender = email_sender
        self.recipient_email = recipient_email
        self.throttler = ExceptionThrottler(session_factory=session_factory)
        self.formatter = ExceptionEmailFormatter()
        # Use ThreadPoolExecutor to prevent thread explosion under exception storm
        self.executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="exception-notifier"
        )

        # In-flight gate: prevents duplicate sends during window between should_send=True and mark_sent()
        # hash -> timestamp when send started
        # Cleanup is lazy and triggered on reserve; TTL bounds memory growth under steady traffic.
        self._inflight: Dict[str, datetime] = {}
        self._inflight_lock = threading.Lock()
        self._inflight_ttl = timedelta(minutes=5)  # Expire stale in-flight entries

    def _reserve_inflight(self, exception_hash: str) -> bool:
        """Try to reserve this hash for sending. Returns True if reserved, False if already in-flight.

        Cleanup is lazy (triggered on reserve) to avoid background thread overhead.
        TTL bounds memory growth under steady traffic.
        """
        with self._inflight_lock:
            # Lazy cleanup: remove expired entries
            now = datetime.now(timezone.utc)
            expired = [
                h for h, ts in self._inflight.items() if now - ts >= self._inflight_ttl
            ]
            for h in expired:
                del self._inflight[h]

            # Check if already in-flight
            if exception_hash in self._inflight:
                return False  # Already being sent by another thread

            # Reserve hash
            self._inflight[exception_hash] = now
            return True

    def _release_inflight(self, exception_hash: str):
        """Release in-flight reservation."""
        with self._inflight_lock:
            self._inflight.pop(exception_hash, None)

    def notify(self, exc: Exception, context: Dict[str, Any]):
        """Send exception notification email (async, non-blocking)."""
        # Submit to thread pool instead of spawning new thread
        self.executor.submit(self._send_notification, exc, context)

    def _send_notification(self, exc: Exception, context: Dict[str, Any]):
        """Internal method to send notification (runs in background thread)."""
        exception_hash = None
        send_ok = False
        try:
            # Generate exception hash
            exc_type = type(exc).__name__
            endpoint = context.get("endpoint", "unknown")
            tb = traceback.extract_tb(exc.__traceback__)
            filename = tb[-1].filename if tb else "unknown"
            lineno = tb[-1].lineno if tb else 0

            exception_hash = hashlib.sha256(
                f"{exc_type}:{endpoint}:{filename}:{lineno}".encode()
            ).hexdigest()[:16]

            # Check throttling (updates DB count, but NOT last_sent_at yet)
            should_send, occurrence_count = self.throttler.should_send(
                exception_hash, exc_type, endpoint
            )
            if not should_send:
                logger.debug(
                    f"[ExceptionNotifier] Skipping notification for {exc_type} (cooldown)"
                )
                return

            # CRITICAL: Check in-flight gate to prevent duplicate sends
            # (between should_send=True and mark_sent(), another thread might also try to send)
            if not self._reserve_inflight(exception_hash):
                logger.debug(
                    f"[ExceptionNotifier] Skipping {exc_type} (already being sent by another thread)"
                )
                return

            # Format traceback
            exc_traceback = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )

            # Format email
            subject, html_body = self.formatter.format_email(
                exc, exc_traceback, context, occurrence_count
            )

            # Send email
            result = self.email_sender.send_email(
                to_email=self.recipient_email,
                subject=subject,
                body=html_body,
                is_html=True,
            )

            if result.get("status") == "success":
                # CRITICAL: Only mark as sent AFTER email succeeds AND DB update succeeds
                send_ok = self.throttler.mark_sent(exception_hash)
                if send_ok:
                    logger.info(
                        f"[ExceptionNotifier] Sent notification for {exc_type} in {endpoint}"
                    )
                else:
                    logger.error(
                        "[ExceptionNotifier] Email sent but failed to update DB - will retry on next occurrence"
                    )
            else:
                # Email failed - do NOT mark as sent, so it can retry later
                # Also do NOT release inflight - let TTL act as backoff
                logger.error(
                    f"[ExceptionNotifier] Failed to send email: {result.get('message')}"
                )

        except Exception as e:
            logger.error(f"[ExceptionNotifier] Error sending notification: {e}")

        finally:
            # CRITICAL: Only release inflight on success
            # If SMTP fails, keep hash in inflight dict to act as backoff (TTL expires in 5 min)
            if exception_hash and send_ok:
                self._release_inflight(exception_hash)
