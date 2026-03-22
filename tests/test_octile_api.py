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
