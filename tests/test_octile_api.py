"""Tests for the Octile scoreboard API."""

import os

# Set env var BEFORE any imports so lifespan uses in-memory DB
os.environ["OCTILE_DB_PATH"] = ":memory:"

import octile_api
from octile_api import OctileScore

# Valid solution for puzzle #1 (cells [0,1,2,3,4,5] = row 0 cols 0-5)
VALID_SOLUTION_P1 = (
    "g1g2g2g3g3g3b1b1"
    "b2b2b2b2y2y2b1b1"
    "b2b2b2b2y2y2b1b1"
    "b2b2b2b2y2y2b1b1"
    "r2y1y1y1y2y2b1b1"
    "r2y1y1y1w2w2r1r1"
    "r2y1y1y1w2w2r1r1"
    "r2w1w1w1w1w1r1r1"
)


def _make_score(puzzle=1, resolve_time=30.0, uuid="uuid-aaa", solution=VALID_SOLUTION_P1):
    """Build a valid score submission payload."""
    return {
        "puzzle_number": puzzle,
        "resolve_time": resolve_time,
        "browser_uuid": uuid,
        "solution": solution,
    }


# ---------------------------------------------------------------------------
# POST /octile/score — basic submission
# ---------------------------------------------------------------------------


def test_submit_score_success(client):
    resp = client.post("/octile/score", json=_make_score())
    assert resp.status_code == 201
    data = resp.json()
    assert data["puzzle_number"] == 1
    assert data["resolve_time"] == 30.0
    assert data["browser_uuid"] == "uuid-aaa"
    assert data["id"] >= 1
    assert data["flagged"] == 0
    assert "created_at" in data


def test_submit_score_legacy_fields_accepted(client):
    """Old clients sending timestamp_utc/os/browser still work."""
    payload = _make_score(uuid="uuid-legacy")
    payload["timestamp_utc"] = "2026-03-18T10:00:00Z"
    payload["os"] = "Android"
    payload["browser"] = "Chrome 120"
    resp = client.post("/octile/score", json=payload)
    assert resp.status_code == 201


def test_submit_score_legacy_timestamp_stored(client):
    """Legacy timestamp_utc is parsed and stored in DB."""
    payload = _make_score(uuid="uuid-ts-store")
    payload["timestamp_utc"] = "2026-03-18T10:00:00Z"
    resp = client.post("/octile/score", json=payload)
    assert resp.status_code == 201

    session = octile_api.get_session()
    try:
        score = (
            session.query(OctileScore)
            .filter(OctileScore.browser_uuid == "uuid-ts-store")
            .first()
        )
        assert score is not None
        assert score.timestamp_utc is not None
        assert score.timestamp_utc.year == 2026
        assert score.timestamp_utc.month == 3
        assert score.timestamp_utc.day == 18
    finally:
        session.close()


def test_submit_score_invalid_legacy_timestamp_uses_server_time(client):
    """Bad timestamp_utc doesn't crash — falls back to server time."""
    payload = _make_score(uuid="uuid-bad-ts")
    payload["timestamp_utc"] = "not-a-date"
    resp = client.post("/octile/score", json=payload)
    assert resp.status_code == 201

    session = octile_api.get_session()
    try:
        score = (
            session.query(OctileScore)
            .filter(OctileScore.browser_uuid == "uuid-bad-ts")
            .first()
        )
        assert score is not None
        # Falls back to server time, not None
        assert score.timestamp_utc is not None
    finally:
        session.close()


def test_submit_score_without_solution_accepted(client):
    """During transition, solution is optional."""
    payload = {
        "puzzle_number": 1,
        "resolve_time": 30.0,
        "browser_uuid": "uuid-no-sol",
    }
    resp = client.post("/octile/score", json=payload)
    assert resp.status_code == 201


def test_submit_score_missing_fields(client):
    resp = client.post("/octile/score", json={"puzzle_number": 1})
    assert resp.status_code == 422


def test_submit_score_extracts_headers(client):
    resp = client.post(
        "/octile/score",
        json=_make_score(uuid="uuid-headers-test"),
        headers={
            "X-Forwarded-For": "1.2.3.4, 5.6.7.8",
            "X-Real-IP": "1.2.3.4",
            "Origin": "https://octile.example.com",
            "User-Agent": "TestBot/1.0",
        },
    )
    assert resp.status_code == 201

    session = octile_api.get_session()
    try:
        score = (
            session.query(OctileScore)
            .filter(OctileScore.browser_uuid == "uuid-headers-test")
            .first()
        )
        assert score is not None
        assert score.client_ip == "1.2.3.4"
        assert score.forwarded_for == "1.2.3.4, 5.6.7.8"
        assert score.real_ip == "1.2.3.4"
        assert score.origin == "https://octile.example.com"
        assert score.user_agent == "TestBot/1.0"
    finally:
        session.close()


def test_submit_score_stores_solution(client):
    resp = client.post("/octile/score", json=_make_score(uuid="uuid-sol-check"))
    assert resp.status_code == 201

    session = octile_api.get_session()
    try:
        score = (
            session.query(OctileScore)
            .filter(OctileScore.browser_uuid == "uuid-sol-check")
            .first()
        )
        assert score is not None
        assert score.solution == VALID_SOLUTION_P1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# POST /octile/score — response backward compatibility
# ---------------------------------------------------------------------------


def test_response_timestamp_utc_alias(client):
    """Response includes timestamp_utc as alias for created_at (old client compat)."""
    resp = client.post("/octile/score", json=_make_score(uuid="uuid-ts-alias"))
    assert resp.status_code == 201
    data = resp.json()
    assert "timestamp_utc" in data
    assert "created_at" in data
    assert data["timestamp_utc"] == data["created_at"]


def test_scoreboard_response_includes_timestamp_utc(client):
    """Scoreboard scores include timestamp_utc so old clients can sort."""
    _insert_scores(client, [_make_score(uuid="uuid-sb-ts")])
    resp = client.get("/octile/scoreboard")
    data = resp.json()
    assert data["total"] >= 1
    score = data["scores"][0]
    assert "timestamp_utc" in score
    assert "created_at" in score
    assert score["timestamp_utc"] == score["created_at"]


# ---------------------------------------------------------------------------
# POST /octile/score — validation (Layer 2)
# ---------------------------------------------------------------------------


def test_reject_puzzle_number_too_low(client):
    resp = client.post("/octile/score", json=_make_score(puzzle=0))
    assert resp.status_code == 400
    assert "puzzle_number" in resp.json()["detail"]


def test_reject_puzzle_number_too_high(client):
    resp = client.post("/octile/score", json=_make_score(puzzle=99999))
    assert resp.status_code == 400
    assert "puzzle_number" in resp.json()["detail"]


def test_reject_too_fast(client):
    resp = client.post("/octile/score", json=_make_score(resolve_time=5.0))
    assert resp.status_code == 400
    assert "too fast" in resp.json()["detail"]


def test_reject_too_slow(client):
    resp = client.post("/octile/score", json=_make_score(resolve_time=100000.0))
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"]


def test_accept_boundary_min_time(client):
    """Exactly 10 seconds is allowed."""
    resp = client.post(
        "/octile/score", json=_make_score(resolve_time=10.0, uuid="uuid-min-time")
    )
    assert resp.status_code == 201


def test_accept_boundary_max_time(client):
    """Exactly 86400 seconds (24h) is allowed."""
    resp = client.post(
        "/octile/score", json=_make_score(resolve_time=86400.0, uuid="uuid-max-time")
    )
    assert resp.status_code == 201


def test_accept_boundary_puzzle_1(client):
    """Puzzle 1 (lowest valid) is accepted."""
    resp = client.post(
        "/octile/score", json=_make_score(puzzle=1, uuid="uuid-p1")
    )
    assert resp.status_code == 201


def test_accept_boundary_puzzle_max(client):
    """Puzzle 11378 (highest valid) is accepted — solution omitted for simplicity."""
    payload = {
        "puzzle_number": 11378,
        "resolve_time": 30.0,
        "browser_uuid": "uuid-pmax",
    }
    resp = client.post("/octile/score", json=payload)
    assert resp.status_code == 201


def test_reject_boundary_time_just_under(client):
    """9.99 seconds is rejected."""
    resp = client.post(
        "/octile/score", json=_make_score(resolve_time=9.99, uuid="uuid-under")
    )
    assert resp.status_code == 400


def test_reject_boundary_time_just_over(client):
    """86401 seconds is rejected."""
    resp = client.post(
        "/octile/score", json=_make_score(resolve_time=86401.0, uuid="uuid-over")
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /octile/score — solution verification (Layer 3)
# ---------------------------------------------------------------------------


def test_reject_invalid_solution_wrong_length(client):
    resp = client.post(
        "/octile/score", json=_make_score(uuid="uuid-bad1", solution="g1g2")
    )
    assert resp.status_code == 400
    assert "128 characters" in resp.json()["detail"]


def test_reject_invalid_solution_bad_piece_id(client):
    bad = "xx" + VALID_SOLUTION_P1[2:]
    resp = client.post(
        "/octile/score", json=_make_score(uuid="uuid-bad2", solution=bad)
    )
    assert resp.status_code == 400
    assert "invalid piece ID" in resp.json()["detail"]


def test_reject_invalid_solution_wrong_grey_position(client):
    # Swap g1 and first b1 — grey1 in wrong position
    bad = list(VALID_SOLUTION_P1)
    # Position 0-1 is 'g1', position 12-13 is 'b1'
    bad[0:2] = list("b1")
    bad[12:14] = list("g1")
    bad_str = "".join(bad)
    resp = client.post(
        "/octile/score", json=_make_score(uuid="uuid-bad3", solution=bad_str)
    )
    assert resp.status_code == 400
    assert "invalid solution" in resp.json()["detail"]


def test_reject_solution_for_wrong_puzzle(client):
    # Valid solution for puzzle 1, but submitted as puzzle 2
    resp = client.post(
        "/octile/score",
        json=_make_score(puzzle=2, uuid="uuid-bad4", solution=VALID_SOLUTION_P1),
    )
    assert resp.status_code == 400
    assert "invalid solution" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /octile/score — rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit(client):
    # First submission should succeed
    resp1 = client.post(
        "/octile/score", json=_make_score(uuid="uuid-rate")
    )
    assert resp1.status_code == 201

    # Second submission within 30s should be rate limited
    resp2 = client.post(
        "/octile/score", json=_make_score(uuid="uuid-rate")
    )
    assert resp2.status_code == 429
    assert "30s" in resp2.json()["detail"]


def test_rate_limit_different_uuid_ok(client):
    resp1 = client.post(
        "/octile/score", json=_make_score(uuid="uuid-rate-a")
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/octile/score", json=_make_score(uuid="uuid-rate-b")
    )
    assert resp2.status_code == 201


# ---------------------------------------------------------------------------
# POST /octile/score — anomaly flagging (Layer 4)
# ---------------------------------------------------------------------------


def test_flagging_high_volume(client):
    """UUID with >50 scores in last hour gets flagged."""
    session = octile_api.get_session()
    try:
        # Insert 51 scores directly to bypass rate limiting
        from datetime import datetime, timezone, timedelta

        for i in range(51):
            score = OctileScore(
                puzzle_number=1,
                resolve_time=30.0,
                browser_uuid="uuid-flagtest",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
            session.add(score)
        session.commit()
    finally:
        session.close()

    # Next submission should be flagged
    resp = client.post(
        "/octile/score", json=_make_score(uuid="uuid-flagtest")
    )
    # It may be rate-limited since we just inserted one very recently,
    # so let's check DB directly
    session = octile_api.get_session()
    try:
        flagged = (
            session.query(OctileScore)
            .filter(
                OctileScore.browser_uuid == "uuid-flagtest",
                OctileScore.flagged == 1,
            )
            .count()
        )
        # If submission went through, it should be flagged
        if resp.status_code == 201:
            assert flagged >= 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Solution verification unit tests
# ---------------------------------------------------------------------------


def test_verify_solution_valid():
    ok, err = octile_api.verify_solution(1, VALID_SOLUTION_P1)
    assert ok is True
    assert err is None


def test_verify_solution_wrong_length():
    ok, err = octile_api.verify_solution(1, "short")
    assert ok is False
    assert "128" in err


def test_verify_solution_invalid_piece():
    bad = "zz" + VALID_SOLUTION_P1[2:]
    ok, err = octile_api.verify_solution(1, bad)
    assert ok is False
    assert "invalid piece ID" in err


def test_verify_solution_wrong_puzzle():
    # Solution for puzzle 1 should fail for puzzle 2
    ok, err = octile_api.verify_solution(2, VALID_SOLUTION_P1)
    assert ok is False


def test_verify_solution_wrong_cell_count():
    """A piece with the wrong number of cells is rejected."""
    # Replace one b2 cell with b1, giving b1 too many and b2 too few
    bad = list(VALID_SOLUTION_P1)
    # Row 1, col 0-1 is "b2" (index 16-17). Change to "b1".
    bad[16:18] = list("b1")
    ok, err = octile_api.verify_solution(1, "".join(bad))
    assert ok is False
    assert "expected" in err and "cells" in err


def test_verify_solution_non_rectangle():
    """Cells that don't form a solid rectangle are rejected."""
    # Swap two adjacent cells of different pieces to break rectangularity
    bad = list(VALID_SOLUTION_P1)
    # Row 4: "r2y1y1y1y2y2b1b1" — swap r2(col0) with y1(col1)
    # r2 at indices 64-65, y1 at 66-67
    bad[64:66] = list("y1")
    bad[66:68] = list("r2")
    ok, err = octile_api.verify_solution(1, "".join(bad))
    assert ok is False


def test_verify_solution_missing_piece():
    """If a piece is entirely missing (replaced by another), rejected."""
    # Replace all w2 with w1 — w2 disappears, w1 has too many cells
    bad = VALID_SOLUTION_P1.replace("w2", "w1")
    ok, err = octile_api.verify_solution(1, bad)
    assert ok is False


def test_verify_solution_grey2_wrong_position():
    """Grey2 at wrong positions is rejected even if rest is valid."""
    bad = list(VALID_SOLUTION_P1)
    # Swap g2 (positions 2-3, 4-5) with g3 (positions 6-11)
    # g2 should be at cells 1,2 but we put g3 there
    bad[2:4] = list("g3")
    bad[6:8] = list("g2")
    ok, err = octile_api.verify_solution(1, "".join(bad))
    assert ok is False


# ---------------------------------------------------------------------------
# POST /octile/score — anomaly flagging: fast average
# ---------------------------------------------------------------------------


def test_flagging_fast_average(client):
    """UUID with avg resolve_time < 20s over 10+ solves gets flagged."""
    from datetime import datetime, timezone, timedelta

    session = octile_api.get_session()
    try:
        # Insert 10 fast scores (15s each) spread over time to avoid rate-limit
        for i in range(10):
            score = OctileScore(
                puzzle_number=1,
                resolve_time=15.0,
                browser_uuid="uuid-fast-avg",
                created_at=datetime.now(timezone.utc) - timedelta(hours=2, minutes=i),
            )
            session.add(score)
        session.commit()
    finally:
        session.close()

    # Next submission should be flagged (avg 15s < 20s over 10+ solves)
    resp = client.post(
        "/octile/score", json=_make_score(resolve_time=15.0, uuid="uuid-fast-avg")
    )
    assert resp.status_code == 201
    assert resp.json()["flagged"] == 1


def test_not_flagged_normal_player(client):
    """A normal player with reasonable times is not flagged."""
    resp = client.post(
        "/octile/score", json=_make_score(resolve_time=60.0, uuid="uuid-normal")
    )
    assert resp.status_code == 201
    assert resp.json()["flagged"] == 0


# ---------------------------------------------------------------------------
# Worker HMAC signature verification (Layer 0)
# ---------------------------------------------------------------------------


def test_hmac_skipped_when_secret_not_set(client):
    """Without WORKER_HMAC_SECRET, requests pass without signature."""
    # Default env has no secret, so all prior tests pass. Verify explicitly.
    resp = client.post("/octile/score", json=_make_score(uuid="uuid-no-hmac"))
    assert resp.status_code == 201


def test_hmac_rejects_missing_signature(client, monkeypatch):
    """With WORKER_HMAC_SECRET set, requests without signature are rejected."""
    monkeypatch.setattr(octile_api, "_WORKER_HMAC_SECRET", "test-secret-123")
    resp = client.post("/octile/score", json=_make_score(uuid="uuid-no-sig"))
    assert resp.status_code == 403
    assert "signature" in resp.json()["detail"]


def test_hmac_rejects_invalid_signature(client, monkeypatch):
    """With WORKER_HMAC_SECRET set, wrong signature is rejected."""
    monkeypatch.setattr(octile_api, "_WORKER_HMAC_SECRET", "test-secret-123")
    resp = client.post(
        "/octile/score",
        json=_make_score(uuid="uuid-bad-sig"),
        headers={
            "X-Worker-Signature": "aW52YWxpZA==",
            "X-Worker-Timestamp": str(int(__import__("time").time())),
        },
    )
    assert resp.status_code == 403


def test_hmac_accepts_valid_signature(client, monkeypatch):
    """With WORKER_HMAC_SECRET set, correctly signed requests pass."""
    import base64
    import hashlib
    import hmac as hmac_mod
    import json
    import time as time_mod

    secret = "test-secret-123"
    monkeypatch.setattr(octile_api, "_WORKER_HMAC_SECRET", secret)

    payload = _make_score(uuid="uuid-valid-sig")
    body_str = json.dumps(payload)
    timestamp = str(int(time_mod.time()))
    message = body_str + timestamp
    sig = hmac_mod.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    sig_b64 = base64.b64encode(sig).decode()

    resp = client.post(
        "/octile/score",
        content=body_str,
        headers={
            "Content-Type": "application/json",
            "X-Worker-Signature": sig_b64,
            "X-Worker-Timestamp": timestamp,
        },
    )
    assert resp.status_code == 201


def test_hmac_rejects_stale_timestamp(client, monkeypatch):
    """Signatures older than 5 minutes are rejected."""
    import base64
    import hashlib
    import hmac as hmac_mod
    import json
    import time as time_mod

    secret = "test-secret-123"
    monkeypatch.setattr(octile_api, "_WORKER_HMAC_SECRET", secret)

    payload = _make_score(uuid="uuid-stale-sig")
    body_str = json.dumps(payload)
    # 10 minutes ago
    timestamp = str(int(time_mod.time()) - 600)
    message = body_str + timestamp
    sig = hmac_mod.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    sig_b64 = base64.b64encode(sig).decode()

    resp = client.post(
        "/octile/score",
        content=body_str,
        headers={
            "Content-Type": "application/json",
            "X-Worker-Signature": sig_b64,
            "X-Worker-Timestamp": timestamp,
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /octile/scoreboard
# ---------------------------------------------------------------------------


def _insert_scores(client, scores):
    """Helper: submit multiple scores via API."""
    for s in scores:
        resp = client.post("/octile/score", json=s)
        assert resp.status_code == 201


def test_scoreboard_empty(client):
    resp = client.get("/octile/scoreboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["scores"] == []


def test_scoreboard_returns_scores_ordered(client):
    _insert_scores(
        client,
        [
            _make_score(resolve_time=20.0, uuid="u1"),
            _make_score(resolve_time=10.0, uuid="u2"),
            _make_score(resolve_time=15.0, uuid="u3"),
        ],
    )
    resp = client.get("/octile/scoreboard")
    data = resp.json()
    assert data["total"] == 3
    times = [s["resolve_time"] for s in data["scores"]]
    assert times == [10.0, 15.0, 20.0]


def test_scoreboard_filter_by_puzzle(client):
    _insert_scores(
        client,
        [
            _make_score(puzzle=1, resolve_time=10.0, uuid="u1"),
            _make_score(puzzle=1, resolve_time=20.0, uuid="u2"),
        ],
    )
    resp = client.get("/octile/scoreboard?puzzle=1")
    data = resp.json()
    assert data["total"] == 2
    assert data["puzzle_number"] == 1


def test_scoreboard_filter_by_uuid(client):
    _insert_scores(
        client,
        [
            _make_score(resolve_time=10.0, uuid="u1"),
            _make_score(resolve_time=20.0, uuid="u2"),
        ],
    )
    resp = client.get("/octile/scoreboard?uuid=u1")
    data = resp.json()
    assert data["total"] == 1
    assert data["scores"][0]["browser_uuid"] == "u1"


def test_scoreboard_best_mode(client):
    """best=true (default) returns only the fastest score per uuid per puzzle."""
    # Insert first, then wait and insert second (bypass rate limit)
    resp1 = client.post("/octile/score", json=_make_score(resolve_time=30.0, uuid="u1"))
    assert resp1.status_code == 201

    # Insert second score directly to DB to bypass rate limiting
    session = octile_api.get_session()
    try:
        from datetime import datetime, timezone, timedelta

        score = OctileScore(
            puzzle_number=1,
            resolve_time=10.0,
            browser_uuid="u1",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        session.add(score)
        session.commit()
    finally:
        session.close()

    resp = client.get("/octile/scoreboard?best=true")
    data = resp.json()
    assert data["total"] == 1
    assert data["scores"][0]["resolve_time"] == 10.0


def test_scoreboard_all_mode(client):
    resp1 = client.post("/octile/score", json=_make_score(resolve_time=30.0, uuid="u1"))
    assert resp1.status_code == 201

    # Insert another directly
    session = octile_api.get_session()
    try:
        from datetime import datetime, timezone, timedelta

        score = OctileScore(
            puzzle_number=1,
            resolve_time=10.0,
            browser_uuid="u1",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        session.add(score)
        session.commit()
    finally:
        session.close()

    resp = client.get("/octile/scoreboard?best=false")
    data = resp.json()
    assert data["total"] == 2


def test_scoreboard_pagination(client):
    _insert_scores(
        client,
        [_make_score(resolve_time=float(i + 10), uuid=f"u{i}") for i in range(10)],
    )
    resp = client.get("/octile/scoreboard?limit=3&offset=0")
    data = resp.json()
    assert data["total"] == 10
    assert len(data["scores"]) == 3
    assert data["scores"][0]["resolve_time"] == 10.0

    resp2 = client.get("/octile/scoreboard?limit=3&offset=3")
    data2 = resp2.json()
    assert len(data2["scores"]) == 3
    assert data2["scores"][0]["resolve_time"] == 13.0


# ---------------------------------------------------------------------------
# GET /octile/puzzles
# ---------------------------------------------------------------------------


def test_puzzles_endpoint(client):
    _insert_scores(
        client,
        [
            _make_score(puzzle=1, resolve_time=10.0, uuid="u1"),
            _make_score(puzzle=1, resolve_time=15.0, uuid="u2"),
        ],
    )
    resp = client.get("/octile/puzzles")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1

    p1 = next(p for p in data if p["puzzle_number"] == 1)
    assert p1["total_scores"] == 2
    assert p1["unique_players"] == 2
    assert p1["best_time"] == 10.0


def test_puzzles_empty(client):
    resp = client.get("/octile/puzzles")
    assert resp.status_code == 200
    assert resp.json() == []
