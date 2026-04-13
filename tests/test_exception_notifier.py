# tests/test_exception_notifier.py
"""
Unit tests for exception notification system.
"""

import pytest
from exception_notifier import ExceptionThrottler, ExceptionEmailFormatter
from datetime import datetime, timedelta, timezone
from db_models import ExceptionLog, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from freezegun import freeze_time


@pytest.fixture
def session_factory(tmp_path):
    """Create file-based temporary SQLite database for multi-thread tests.

    CRITICAL: Uses NullPool so each session gets a fresh connection.
    This realistically tests BEGIN IMMEDIATE + lock contention across threads.
    StaticPool would serialize access and hide race conditions.
    """
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"timeout": 30},
        poolclass=NullPool,  # Each session gets new connection (most realistic for concurrency tests)
    )
    Base.metadata.create_all(engine)

    # Create session factory that tests will inject into throttler
    SessionLocal = sessionmaker(bind=engine)
    yield SessionLocal

    # Cleanup
    engine.dispose()
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
def throttler(session_factory):
    """Create throttler with injected session factory."""
    return ExceptionThrottler(session_factory=session_factory)


def test_same_exception_hash_in_cooldown_no_send(throttler):
    """TEST 1: Same exception hash within cooldown should not send email."""
    # First occurrence - should send
    should_send, count = throttler.should_send("hash123", "ValueError", "GET /api/test")
    assert should_send is True
    assert count == 1

    # Second occurrence immediately - should NOT send (within 1h cooldown)
    should_send, count = throttler.should_send("hash123", "ValueError", "GET /api/test")
    assert should_send is False
    assert count == 2


def test_count_exceeds_3_cooldown_becomes_6h(throttler):
    """TEST 2: When count exceeds 3, cooldown should switch to 6 hours."""
    base_time = datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)

    # First occurrence
    with freeze_time(base_time):
        should_send, count = throttler.should_send(
            "hash456", "KeyError", "POST /api/submit"
        )
        assert should_send is True
        assert count == 1

    # 2nd occurrence after 1h1m - should send (past 1h cooldown)
    with freeze_time(base_time + timedelta(hours=1, minutes=1)):
        should_send, count = throttler.should_send(
            "hash456", "KeyError", "POST /api/submit"
        )
        assert should_send is True
        assert count == 2

    # 3rd occurrence after another 1h1m - should send
    with freeze_time(base_time + timedelta(hours=2, minutes=2)):
        should_send, count = throttler.should_send(
            "hash456", "KeyError", "POST /api/submit"
        )
        assert should_send is True
        assert count == 3

    # 4th occurrence 1h later - cooldown NOW 6h, so should NOT send
    with freeze_time(base_time + timedelta(hours=3, minutes=2)):
        should_send, count = throttler.should_send(
            "hash456", "KeyError", "POST /api/submit"
        )
        assert should_send is False  # Within 6h cooldown
        assert count == 4

    # 5th occurrence 6h1m after 3rd send - should send now
    with freeze_time(base_time + timedelta(hours=8, minutes=3)):
        should_send, count = throttler.should_send(
            "hash456", "KeyError", "POST /api/submit"
        )
        assert should_send is True
        assert count == 5


def test_cache_count_syncs_with_db_prevents_early_send(throttler, session_factory):
    """TEST 3: Cache count should sync with DB to prevent using stale count."""
    # First occurrence
    should_send, count = throttler.should_send("hash789", "TypeError", "GET /api/data")
    assert should_send is True
    assert count == 1

    # Trigger multiple occurrences within cooldown (count increments in DB)
    for _ in range(5):
        should_send, count = throttler.should_send(
            "hash789", "TypeError", "GET /api/data"
        )
        assert should_send is False  # All should be blocked

    # Verify cache has latest count
    assert throttler.cache["hash789"][1] == 6  # count should be 6, not stuck at 1

    # Verify DB has correct count
    session = session_factory()
    log = session.query(ExceptionLog).filter_by(exception_hash="hash789").first()
    assert log.count == 6
    session.close()


def test_email_html_escaping():
    """Test HTML escaping prevents injection."""
    formatter = ExceptionEmailFormatter()

    exc = ValueError("<script>alert('xss')</script>")
    context = {
        "endpoint": "GET /test?param=<b>bold</b>",
        "method": "GET",
        "user_id": "user<tag>",
        "ip_address": "1.2.3.4",
        "timestamp": "2026-04-13T12:00:00Z",
        "hostname": "test-host",
        "python_version": "3.10",
        "platform": "Linux",
    }

    subject, html_body = formatter.format_email(exc, "traceback <here>", context, 1)

    # All user content should be escaped
    assert "&lt;script&gt;" in html_body
    assert "&lt;b&gt;" in html_body
    assert "&lt;tag&gt;" in html_body
    assert "<script>" not in html_body  # NOT raw HTML


def test_subject_crlf_injection_prevention():
    """Test CRLF characters are stripped from email subject."""
    formatter = ExceptionEmailFormatter()

    exc = ValueError("malicious\r\nBcc: hacker@evil.com")
    context = {
        "endpoint": "GET /api\r\ninjection",
        "method": "GET",
        "user_id": None,
        "ip_address": "1.2.3.4",
        "timestamp": "2026-04-13T12:00:00Z",
        "hostname": "test-host",
        "python_version": "3.10",
        "platform": "Linux",
    }

    subject, html_body = formatter.format_email(exc, "traceback", context, 1)

    # Subject should NOT contain \r or \n
    assert "\r" not in subject
    assert "\n" not in subject
    assert "Bcc:" not in subject  # The injection attempt should be neutralized


def test_race_condition_prevention_concurrent_sends(session_factory):
    """TEST 4: Verify BEGIN IMMEDIATE + in-flight gate prevent duplicate email sends in race condition."""
    import threading
    from unittest.mock import Mock
    from exception_notifier import ExceptionNotifier

    # Mock email sender to count actual send attempts
    mock_email_sender = Mock()
    mock_email_sender.send_email = Mock(return_value={"status": "success"})

    # Create notifier with mocked sender
    notifier = ExceptionNotifier(
        email_sender=mock_email_sender,
        recipient_email="test@example.com",
        session_factory=session_factory,
    )

    # Create test exception
    try:
        raise ValueError("Race test error")
    except ValueError as e:
        test_exc = e

    # Barrier to ensure all threads start simultaneously (more deterministic race)
    barrier = threading.Barrier(5)

    def send_with_barrier(exc, ctx):
        """Wrapper to synchronize thread start."""
        barrier.wait()  # All threads wait here until all 5 arrive
        notifier._send_notification(exc, ctx)

    # Launch 5 threads simultaneously with same exception
    threads = []
    for _ in range(5):
        context = {
            "endpoint": "GET /race",
            "method": "GET",
            "user_id": None,
            "ip_address": "1.2.3.4",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": "test",
            "python_version": "3.10",
            "platform": "Linux",
        }
        t = threading.Thread(target=send_with_barrier, args=(test_exc, context))
        threads.append(t)

    # Start all threads (they will synchronize at barrier)
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # CRITICAL: Verify only ONE actual email was sent (not 5)
    assert mock_email_sender.send_email.call_count == 1, (
        f"Expected 1 email send, got {mock_email_sender.send_email.call_count}"
    )

    # Verify: DB recorded all 5 occurrences
    session = session_factory()
    logs = session.query(ExceptionLog).all()
    assert len(logs) == 1  # One unique exception
    assert logs[0].count == 5  # All 5 threads incremented the count
    session.close()
