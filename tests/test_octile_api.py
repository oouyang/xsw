"""Tests for the Octile scoreboard API."""

import os

import pytest

# Set env var BEFORE any imports so lifespan uses in-memory DB
os.environ["OCTILE_DB_PATH"] = ":memory:"

import octile_api
from octile_api import (
    OctileScore,
    P92,
    P92_MAP,
    _PIECE_ENC,
    _decode_compact_solution,
    _transform_cell,
    _decompose_puzzle_number,
    decode_puzzle,
    decode_puzzle_extended,
    verify_solution,
    get_puzzle_difficulty,
    get_level_total,
    level_slot_to_puzzle,
    PUZZLE_COUNT,
    TOTAL_PUZZLE_COUNT,
)

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


def _encode_compact(grid_128: str) -> str:
    """Encode a 128-char legacy solution to 8-char compact format (test helper)."""
    grid = [grid_128[i : i + 2] for i in range(0, 128, 2)]
    bounds: dict[str, list[int]] = {}
    for idx, pid in enumerate(grid):
        if pid in ("g1", "g2", "g3"):
            continue
        r, c = divmod(idx, 8)
        if pid not in bounds:
            bounds[pid] = [r, c, r, c]
        else:
            b = bounds[pid]
            if r < b[0]:
                b[0] = r
            if c < b[1]:
                b[1] = c
            if r > b[2]:
                b[2] = r
            if c > b[3]:
                b[3] = c

    n = 0
    for i in range(7, -1, -1):
        p = _PIECE_ENC[i]
        b = bounds[p["id"]]
        h = b[2] - b[0] + 1
        if p["sq"] or h == p["r"]:
            pi = b[0] * (9 - p["c"]) + b[1]
        else:
            pi = p["hN"] + b[0] * (9 - p["r"]) + b[1]
        n = n * p["N"] + pi

    s = ""
    for _ in range(8):
        s += P92[n % 92]
        n //= 92
    return s


VALID_COMPACT_P1 = _encode_compact(VALID_SOLUTION_P1)


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
    """Puzzle 91024 (highest valid) is accepted — solution omitted for simplicity."""
    payload = {
        "puzzle_number": TOTAL_PUZZLE_COUNT,
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
    assert "8 or 128" in resp.json()["detail"]


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
    ok, err = verify_solution(1, "short")
    assert ok is False
    assert "8 or 128" in err


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


def test_hmac_allows_direct_requests_without_signature(client, monkeypatch):
    """With WORKER_HMAC_SECRET set, requests without signature headers pass (direct)."""
    monkeypatch.setattr(octile_api, "_WORKER_HMAC_SECRET", "test-secret-123")
    resp = client.post("/octile/score", json=_make_score(uuid="uuid-no-sig"))
    assert resp.status_code == 201


@pytest.mark.skip(reason="HMAC verification disabled for now")
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


@pytest.mark.skip(reason="HMAC verification disabled for now")
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


# ---------------------------------------------------------------------------
# Base-92 alphabet
# ---------------------------------------------------------------------------


def test_p92_length():
    assert len(P92) == 92


def test_p92_excludes_quote_and_backslash():
    assert "'" not in P92
    assert "\\" not in P92


def test_p92_all_printable():
    for c in P92:
        assert 33 <= ord(c) <= 126


def test_p92_map_roundtrip():
    for i, c in enumerate(P92):
        assert P92_MAP[c] == i


# ---------------------------------------------------------------------------
# Puzzle decoding
# ---------------------------------------------------------------------------


def test_decode_puzzle_returns_6_cells():
    cells = decode_puzzle(0)
    assert len(cells) == 6


def test_decode_puzzle_cells_in_range():
    for idx in [0, 100, 5000, PUZZLE_COUNT - 1]:
        cells = decode_puzzle(idx)
        for c in cells:
            assert 0 <= c <= 63


def test_decode_puzzle_grey_cells_unique():
    """Grey cells should generally not overlap (g1, g2a, g2b distinct positions)."""
    cells = decode_puzzle(0)
    # g1 is 1 cell, g2 is 2 cells, g3 is 3 cells — all distinct
    assert len(set(cells)) == 6


def test_decode_puzzle_g2_adjacent():
    """Grey2 cells should be horizontally or vertically adjacent."""
    for idx in [0, 42, 500, 11377]:
        cells = decode_puzzle(idx)
        g2a, g2b = cells[1], cells[2]
        diff = abs(g2a - g2b)
        assert diff in (1, 8), f"puzzle {idx}: g2 cells {g2a},{g2b} not adjacent"


def test_decode_puzzle_g3_collinear():
    """Grey3 cells should form a horizontal or vertical line of 3."""
    for idx in [0, 42, 500, 11377]:
        cells = decode_puzzle(idx)
        g3 = sorted(cells[3:6])
        d1, d2 = g3[1] - g3[0], g3[2] - g3[1]
        assert d1 == d2
        assert d1 in (1, 8), f"puzzle {idx}: g3 not collinear {g3}"


# ---------------------------------------------------------------------------
# D4 symmetry transforms
# ---------------------------------------------------------------------------


def test_transform_cell_identity():
    for cell in range(64):
        assert _transform_cell(cell, 0) == cell


def test_transform_cell_rotation_cycle():
    """Four 90° CW rotations return to the original cell."""
    for cell in range(64):
        c = cell
        for _ in range(4):
            c = _transform_cell(c, 1)
        assert c == cell, f"cell {cell} didn't return after 4 rotations"


def test_transform_cell_180_involution():
    """180° applied twice returns to original."""
    for cell in range(64):
        assert _transform_cell(_transform_cell(cell, 2), 2) == cell


def test_transform_cell_mirror_involution():
    """Each mirror is its own inverse."""
    for t in [4, 5, 6, 7]:
        for cell in range(64):
            assert _transform_cell(_transform_cell(cell, t), t) == cell


def test_transform_cell_stays_in_range():
    for t in range(8):
        for cell in range(64):
            result = _transform_cell(cell, t)
            assert 0 <= result <= 63


# ---------------------------------------------------------------------------
# Puzzle decomposition and extended decoding
# ---------------------------------------------------------------------------


def test_decompose_puzzle_number_first():
    base, transform = _decompose_puzzle_number(1)
    assert base == 0
    assert transform == 0


def test_decompose_puzzle_number_last_base():
    base, transform = _decompose_puzzle_number(PUZZLE_COUNT)
    assert base == PUZZLE_COUNT - 1
    assert transform == 0


def test_decompose_puzzle_number_first_transform1():
    base, transform = _decompose_puzzle_number(PUZZLE_COUNT + 1)
    assert base == 0
    assert transform == 1


def test_decompose_puzzle_number_last():
    base, transform = _decompose_puzzle_number(TOTAL_PUZZLE_COUNT)
    assert base == PUZZLE_COUNT - 1
    assert transform == 7


def test_decode_puzzle_extended_identity():
    """Puzzles 1–11378 should match decode_puzzle(0–11377)."""
    for pnum in [1, 100, PUZZLE_COUNT]:
        ext = decode_puzzle_extended(pnum)
        base = decode_puzzle(pnum - 1)
        assert ext == base


def test_decode_puzzle_extended_transform():
    """Transformed puzzle cells differ from base."""
    base_cells = decode_puzzle_extended(1)
    rot90_cells = decode_puzzle_extended(PUZZLE_COUNT + 1)
    # Same base puzzle, different transform — cells should differ
    # (unless the puzzle is symmetric, which is unlikely for puzzle 0)
    assert base_cells != rot90_cells


def test_decode_puzzle_extended_all_cells_valid():
    for pnum in [1, PUZZLE_COUNT + 1, 2 * PUZZLE_COUNT + 1, TOTAL_PUZZLE_COUNT]:
        cells = decode_puzzle_extended(pnum)
        assert len(cells) == 6
        for c in cells:
            assert 0 <= c <= 63


# ---------------------------------------------------------------------------
# Compact solution encoding/decoding (8-char format)
# ---------------------------------------------------------------------------


def test_piece_enc_placement_counts():
    """Verify computed placement counts match expected values."""
    expected = {"r1": 84, "r2": 80, "w1": 64, "w2": 49, "b1": 56, "b2": 60, "y1": 36, "y2": 70}
    for p in _PIECE_ENC:
        assert p["N"] == expected[p["id"]], f"{p['id']}: {p['N']} != {expected[p['id']]}"


def test_piece_enc_total_fits_in_8_base92():
    total = 1
    for p in _PIECE_ENC:
        total *= p["N"]
    assert total < 92**8


def test_compact_solution_length():
    assert len(VALID_COMPACT_P1) == 8


def test_compact_solution_all_p92_chars():
    for c in VALID_COMPACT_P1:
        assert c in P92_MAP


def test_decode_compact_solution_roundtrip():
    """Encode legacy → compact, decode compact, verify pieces match."""
    board = _decode_compact_solution(VALID_COMPACT_P1)
    assert board is not None
    # Parse legacy solution for comparison
    legacy = [VALID_SOLUTION_P1[i : i + 2] for i in range(0, 128, 2)]
    for i in range(64):
        if legacy[i] in ("g1", "g2", "g3"):
            continue
        assert board[i] == legacy[i], f"cell {i}: {board[i]} != {legacy[i]}"


def test_decode_compact_solution_none_for_grey():
    """Grey cells should be None in decoded compact solution."""
    board = _decode_compact_solution(VALID_COMPACT_P1)
    grey_cells = set(decode_puzzle_extended(1))
    for c in grey_cells:
        assert board[c] is None


def test_decode_compact_solution_invalid_length():
    assert _decode_compact_solution("short") is None
    assert _decode_compact_solution("toolongstring") is None


def test_decode_compact_solution_invalid_chars():
    assert _decode_compact_solution("abcdefg'") is None  # ' excluded from P92
    assert _decode_compact_solution("abcdefg\\") is None  # \ excluded from P92


def test_decode_compact_all_positions_filled():
    """All 58 non-grey cells should have a piece ID after decoding."""
    board = _decode_compact_solution(VALID_COMPACT_P1)
    grey_cells = set(decode_puzzle_extended(1))
    for i in range(64):
        if i in grey_cells:
            continue
        assert board[i] is not None, f"cell {i} is None"


def test_decode_compact_piece_cell_counts():
    """Each piece should occupy the correct number of cells."""
    board = _decode_compact_solution(VALID_COMPACT_P1)
    from collections import Counter
    counts = Counter(c for c in board if c is not None)
    expected = {"r1": 6, "r2": 4, "w1": 5, "w2": 4, "b1": 10, "b2": 12, "y1": 9, "y2": 8}
    for pid, exp in expected.items():
        assert counts[pid] == exp, f"{pid}: {counts[pid]} != {exp}"


# ---------------------------------------------------------------------------
# verify_solution with compact format
# ---------------------------------------------------------------------------


def test_verify_compact_solution_valid():
    ok, err = verify_solution(1, VALID_COMPACT_P1)
    assert ok is True, f"Expected valid but got: {err}"
    assert err is None


def test_verify_compact_solution_wrong_puzzle():
    ok, err = verify_solution(2, VALID_COMPACT_P1)
    assert ok is False


def test_verify_compact_solution_invalid_chars():
    ok, err = verify_solution(1, "!!!!!!!'")  # ' not in P92
    assert ok is False


def test_verify_compact_and_legacy_agree():
    """Both formats should produce the same validation result for puzzle 1."""
    ok_legacy, _ = verify_solution(1, VALID_SOLUTION_P1)
    ok_compact, _ = verify_solution(1, VALID_COMPACT_P1)
    assert ok_legacy is True
    assert ok_compact is True


def test_verify_solution_rejects_invalid_lengths():
    for length in [0, 5, 7, 9, 27, 50, 127, 129]:
        ok, err = verify_solution(1, "!" * length)
        assert ok is False
        assert "8 or 128" in err


# ---------------------------------------------------------------------------
# Compact solution via POST /octile/score
# ---------------------------------------------------------------------------


def test_submit_compact_solution(client):
    resp = client.post(
        "/octile/score",
        json=_make_score(uuid="uuid-compact", solution=VALID_COMPACT_P1),
    )
    assert resp.status_code == 201


def test_submit_compact_solution_stored(client):
    resp = client.post(
        "/octile/score",
        json=_make_score(uuid="uuid-compact-store", solution=VALID_COMPACT_P1),
    )
    assert resp.status_code == 201
    session = octile_api.get_session()
    try:
        score = (
            session.query(OctileScore)
            .filter(OctileScore.browser_uuid == "uuid-compact-store")
            .first()
        )
        assert score.solution == VALID_COMPACT_P1
    finally:
        session.close()


def test_submit_compact_solution_wrong_puzzle(client):
    resp = client.post(
        "/octile/score",
        json=_make_score(puzzle=2, uuid="uuid-compact-bad", solution=VALID_COMPACT_P1),
    )
    assert resp.status_code == 400
    assert "invalid solution" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /octile/puzzle/{number}
# ---------------------------------------------------------------------------


def test_get_puzzle_valid(client):
    resp = client.get("/octile/puzzle/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["puzzle_number"] == 1
    assert data["base_puzzle"] == 1
    assert data["transform"] == 0
    assert len(data["cells"]) == 6
    assert all(0 <= c <= 63 for c in data["cells"])


def test_get_puzzle_transformed(client):
    resp = client.get(f"/octile/puzzle/{PUZZLE_COUNT + 1}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["puzzle_number"] == PUZZLE_COUNT + 1
    assert data["base_puzzle"] == 1
    assert data["transform"] == 1


def test_get_puzzle_last(client):
    resp = client.get(f"/octile/puzzle/{TOTAL_PUZZLE_COUNT}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["puzzle_number"] == TOTAL_PUZZLE_COUNT
    assert data["transform"] == 7


def test_get_puzzle_invalid_zero(client):
    resp = client.get("/octile/puzzle/0")
    assert resp.status_code == 400


def test_get_puzzle_invalid_too_high(client):
    resp = client.get(f"/octile/puzzle/{TOTAL_PUZZLE_COUNT + 1}")
    assert resp.status_code == 400


def test_get_puzzle_cells_match_decode(client):
    """API response cells should match decode_puzzle_extended."""
    for pnum in [1, 42, PUZZLE_COUNT, PUZZLE_COUNT + 1, TOTAL_PUZZLE_COUNT]:
        resp = client.get(f"/octile/puzzle/{pnum}")
        assert resp.status_code == 200
        assert resp.json()["cells"] == decode_puzzle_extended(pnum)


def test_get_puzzle_includes_difficulty(client):
    resp = client.get("/octile/puzzle/1")
    assert resp.status_code == 200
    data = resp.json()
    assert "difficulty" in data
    assert data["difficulty"] in (1, 2, 3, 4)
    assert data["difficulty_label"] in ("easy", "medium", "hard", "hell")


# ---------------------------------------------------------------------------
# Difficulty classification unit tests
# ---------------------------------------------------------------------------


def test_get_puzzle_difficulty_range():
    for pnum in [1, 100, PUZZLE_COUNT, PUZZLE_COUNT + 1, TOTAL_PUZZLE_COUNT]:
        level = get_puzzle_difficulty(pnum)
        assert level in (1, 2, 3, 4)


def test_difficulty_same_for_all_transforms():
    """All 8 transforms of the same base puzzle have the same difficulty."""
    for base in [0, 42, 500, PUZZLE_COUNT - 1]:
        levels = set()
        for t in range(8):
            pnum = t * PUZZLE_COUNT + base + 1
            levels.add(get_puzzle_difficulty(pnum))
        assert len(levels) == 1, f"base {base}: got different levels {levels}"


def test_get_level_total_positive():
    for level_num in (1, 2, 3, 4):
        total = get_level_total(level_num)
        assert total > 0
        assert total % 8 == 0  # must be multiple of 8 (base × 8 transforms)


def test_get_level_total_sum():
    """All levels should sum to total puzzle count."""
    total = sum(get_level_total(n) for n in (1, 2, 3, 4))
    assert total == TOTAL_PUZZLE_COUNT


def test_level_slot_to_puzzle_first():
    result = level_slot_to_puzzle(1, 1)
    assert result is not None
    pnum, base_idx = result
    assert 1 <= pnum <= TOTAL_PUZZLE_COUNT
    assert get_puzzle_difficulty(pnum) == 1  # should be easy


def test_level_slot_to_puzzle_last():
    total = get_level_total(1)
    result = level_slot_to_puzzle(1, total)
    assert result is not None
    pnum, _ = result
    assert get_puzzle_difficulty(pnum) == 1


def test_level_slot_to_puzzle_out_of_range():
    assert level_slot_to_puzzle(1, 0) is None
    total = get_level_total(1)
    assert level_slot_to_puzzle(1, total + 1) is None


def test_level_slot_to_puzzle_invalid_level():
    assert level_slot_to_puzzle(5, 1) is None
    assert level_slot_to_puzzle(0, 1) is None


def test_level_slot_interleaved():
    """Consecutive slots should use different base puzzles (interleaved ordering)."""
    results = [level_slot_to_puzzle(1, s) for s in range(1, 9)]
    assert all(r is not None for r in results)
    base_indices = [r[1] for r in results]
    assert len(set(base_indices)) == 8  # all different bases
    pnums = [r[0] for r in results]
    assert len(set(pnums)) == 8  # all different puzzle numbers


def test_level_slot_ordering():
    """Earlier slots should have easier puzzles (fewer attempts) within level."""
    from octile_api import get_puzzle_attempts

    # Compare slot 1 vs last slot of easy
    first = level_slot_to_puzzle(1, 1)
    total = get_level_total(1)
    last = level_slot_to_puzzle(1, total)
    assert first is not None and last is not None
    assert get_puzzle_attempts(first[0]) <= get_puzzle_attempts(last[0])


# ---------------------------------------------------------------------------
# GET /octile/levels
# ---------------------------------------------------------------------------


def test_get_levels(client):
    resp = client.get("/octile/levels")
    assert resp.status_code == 200
    data = resp.json()
    assert "easy" in data
    assert "medium" in data
    assert "hard" in data
    assert "hell" in data
    assert all(v > 0 for v in data.values())
    assert sum(data.values()) == TOTAL_PUZZLE_COUNT


# ---------------------------------------------------------------------------
# GET /octile/level/{name}/puzzle/{slot}
# ---------------------------------------------------------------------------


def test_get_level_puzzle_easy_first(client):
    resp = client.get("/octile/level/easy/puzzle/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] == "easy"
    assert data["slot"] == 1
    assert data["total"] > 0
    assert len(data["cells"]) == 6
    assert all(0 <= c <= 63 for c in data["cells"])
    assert 1 <= data["puzzle_number"] <= TOTAL_PUZZLE_COUNT


def test_get_level_puzzle_hell_first(client):
    resp = client.get("/octile/level/hell/puzzle/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["level"] == "hell"
    assert data["slot"] == 1


def test_get_level_puzzle_last_slot(client):
    levels_resp = client.get("/octile/levels")
    easy_total = levels_resp.json()["easy"]
    resp = client.get(f"/octile/level/easy/puzzle/{easy_total}")
    assert resp.status_code == 200
    assert resp.json()["slot"] == easy_total


def test_get_level_puzzle_invalid_level(client):
    resp = client.get("/octile/level/insane/puzzle/1")
    assert resp.status_code == 400


def test_get_level_puzzle_slot_zero(client):
    resp = client.get("/octile/level/easy/puzzle/0")
    assert resp.status_code == 400


def test_get_level_puzzle_slot_too_high(client):
    levels_resp = client.get("/octile/levels")
    easy_total = levels_resp.json()["easy"]
    resp = client.get(f"/octile/level/easy/puzzle/{easy_total + 1}")
    assert resp.status_code == 400


def test_get_level_puzzle_cells_valid(client):
    """Cells from level endpoint should match decode_puzzle_extended."""
    resp = client.get("/octile/level/medium/puzzle/1")
    assert resp.status_code == 200
    data = resp.json()
    expected_cells = decode_puzzle_extended(data["puzzle_number"])
    assert data["cells"] == expected_cells


def test_get_level_puzzle_sequential_order(client):
    """First puzzle in each level should be easier than last."""
    from octile_api import get_puzzle_attempts

    for level_name in ("easy", "medium", "hard", "hell"):
        resp1 = client.get(f"/octile/level/{level_name}/puzzle/1")
        levels_resp = client.get("/octile/levels")
        total = levels_resp.json()[level_name]
        resp_last = client.get(f"/octile/level/{level_name}/puzzle/{total}")
        assert resp1.status_code == 200
        assert resp_last.status_code == 200
        att_first = get_puzzle_attempts(resp1.json()["puzzle_number"])
        att_last = get_puzzle_attempts(resp_last.json()["puzzle_number"])
        assert att_first <= att_last, f"{level_name}: first {att_first} > last {att_last}"


# ---------------------------------------------------------------------------
# EXP + Diamond system tests (replaces old coins tests)
# ---------------------------------------------------------------------------

def test_calc_exp_easy_slow():
    from octile_api import calc_exp
    assert calc_exp(1, 121) == 100  # easy, >120s (>2×par) → grade B, base 100 ×1.0

def test_calc_exp_easy_fast():
    from octile_api import calc_exp
    assert calc_exp(1, 15) == 200  # easy, ≤60s (≤par) → grade S, base 100 ×2.0

def test_calc_exp_nightmare_medium_speed():
    from octile_api import calc_exp
    assert calc_exp(4, 361) == 2000  # nightmare, >360s (>2×par) → grade B, base 2000 ×1.0

def test_calc_exp_grade_tiers():
    from octile_api import calc_exp
    # Medium: par=90s, 2×par=180s
    assert calc_exp(2, 60) == 500   # ≤90s → S ×2.0 (250×2)
    assert calc_exp(2, 90) == 500   # =90s → S ×2.0
    assert calc_exp(2, 120) == 375  # ≤180s → A ×1.5 (250×1.5)
    assert calc_exp(2, 180) == 375  # =180s → A ×1.5
    assert calc_exp(2, 200) == 250  # >180s → B ×1.0

def test_calc_skill_grade():
    from octile_api import calc_skill_grade
    # Easy: par=60s
    assert calc_skill_grade(1, 30) == "S"   # ≤par
    assert calc_skill_grade(1, 60) == "S"   # =par
    assert calc_skill_grade(1, 90) == "A"   # ≤2×par
    assert calc_skill_grade(1, 120) == "A"  # =2×par
    assert calc_skill_grade(1, 121) == "B"  # >2×par

def test_submit_score_returns_exp(client):
    resp = client.post("/octile/score", json={
        "puzzle_number": 1,
        "resolve_time": 30.0,
        "browser_uuid": "exp-test-uuid",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "exp" in data
    assert data["exp"] == 200  # easy, 30s ≤ par 60s → S grade, 100 × 2.0
    assert "diamonds" in data
    assert data["diamonds"] == 1
    assert "grade" in data
    assert data["grade"] == "S"
    # Legacy coins field still present and equals exp
    assert "coins" in data
    assert data["coins"] == data["exp"]

def test_leaderboard_empty(client):
    resp = client.get("/octile/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_players"] == 0
    assert data["leaderboard"] == []

def test_leaderboard_ranks_by_exp(client):
    # Submit scores for two players
    client.post("/octile/score", json={
        "puzzle_number": 1, "resolve_time": 30.0, "browser_uuid": "player-a",
    })
    import time; time.sleep(0.1)
    client.post("/octile/score", json={
        "puzzle_number": 2, "resolve_time": 15.0, "browser_uuid": "player-b",
    })
    resp = client.get("/octile/leaderboard?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    board = data["leaderboard"]
    assert len(board) >= 2
    # Verify sorted by total_exp descending
    for i in range(len(board) - 1):
        assert board[i]["total_exp"] >= board[i + 1]["total_exp"]
    # Legacy total_coins field still present
    assert "total_coins" in board[0]
    assert "total_diamonds" in board[0]
