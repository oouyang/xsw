"""Tests for the Octile scoreboard API."""

import os

# Set env var BEFORE any imports so lifespan uses in-memory DB
os.environ["OCTILE_DB_PATH"] = ":memory:"

import octile_api
from octile_api import OctileScore


# ---------------------------------------------------------------------------
# POST /octile/score
# ---------------------------------------------------------------------------


def test_submit_score_success(client):
    resp = client.post(
        "/octile/score",
        json={
            "puzzle_number": 1,
            "resolve_time": 12.345,
            "browser_uuid": "uuid-aaa",
            "timestamp_utc": "2026-03-18T10:00:00Z",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["puzzle_number"] == 1
    assert data["resolve_time"] == 12.345
    assert data["browser_uuid"] == "uuid-aaa"
    assert data["id"] >= 1


def test_submit_score_with_optional_fields(client):
    resp = client.post(
        "/octile/score",
        json={
            "puzzle_number": 2,
            "resolve_time": 5.0,
            "browser_uuid": "uuid-bbb",
            "timestamp_utc": "2026-03-18T10:00:00+00:00",
            "os": "Windows 11",
            "browser": "Chrome 120",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["os"] == "Windows 11"
    assert data["browser"] == "Chrome 120"


def test_submit_score_missing_fields(client):
    resp = client.post(
        "/octile/score",
        json={"puzzle_number": 1},
    )
    assert resp.status_code == 422


def test_submit_score_extracts_headers(client):
    resp = client.post(
        "/octile/score",
        json={
            "puzzle_number": 99,
            "resolve_time": 10.0,
            "browser_uuid": "uuid-headers-test",
            "timestamp_utc": "2026-03-18T10:00:00Z",
        },
        headers={
            "X-Forwarded-For": "1.2.3.4, 5.6.7.8",
            "X-Real-IP": "1.2.3.4",
            "Origin": "https://octile.example.com",
            "User-Agent": "TestBot/1.0",
        },
    )
    assert resp.status_code == 201

    # Verify stored values in DB by filtering on the unique uuid
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
            {
                "puzzle_number": 1,
                "resolve_time": 20.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:00:00Z",
            },
            {
                "puzzle_number": 1,
                "resolve_time": 10.0,
                "browser_uuid": "u2",
                "timestamp_utc": "2026-03-18T10:01:00Z",
            },
            {
                "puzzle_number": 1,
                "resolve_time": 15.0,
                "browser_uuid": "u3",
                "timestamp_utc": "2026-03-18T10:02:00Z",
            },
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
            {
                "puzzle_number": 1,
                "resolve_time": 10.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:00:00Z",
            },
            {
                "puzzle_number": 2,
                "resolve_time": 20.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:01:00Z",
            },
        ],
    )
    resp = client.get("/octile/scoreboard?puzzle=1")
    data = resp.json()
    assert data["total"] == 1
    assert data["scores"][0]["puzzle_number"] == 1
    assert data["puzzle_number"] == 1


def test_scoreboard_filter_by_uuid(client):
    _insert_scores(
        client,
        [
            {
                "puzzle_number": 1,
                "resolve_time": 10.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:00:00Z",
            },
            {
                "puzzle_number": 1,
                "resolve_time": 20.0,
                "browser_uuid": "u2",
                "timestamp_utc": "2026-03-18T10:01:00Z",
            },
        ],
    )
    resp = client.get("/octile/scoreboard?uuid=u1")
    data = resp.json()
    assert data["total"] == 1
    assert data["scores"][0]["browser_uuid"] == "u1"


def test_scoreboard_best_mode(client):
    """best=true (default) returns only the fastest score per uuid per puzzle."""
    _insert_scores(
        client,
        [
            {
                "puzzle_number": 1,
                "resolve_time": 30.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:00:00Z",
            },
            {
                "puzzle_number": 1,
                "resolve_time": 10.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:01:00Z",
            },
            {
                "puzzle_number": 1,
                "resolve_time": 20.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:02:00Z",
            },
        ],
    )
    resp = client.get("/octile/scoreboard?best=true")
    data = resp.json()
    assert data["total"] == 1
    assert data["scores"][0]["resolve_time"] == 10.0


def test_scoreboard_all_mode(client):
    """best=false returns all scores."""
    _insert_scores(
        client,
        [
            {
                "puzzle_number": 1,
                "resolve_time": 30.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:00:00Z",
            },
            {
                "puzzle_number": 1,
                "resolve_time": 10.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:01:00Z",
            },
        ],
    )
    resp = client.get("/octile/scoreboard?best=false")
    data = resp.json()
    assert data["total"] == 2


def test_scoreboard_pagination(client):
    _insert_scores(
        client,
        [
            {
                "puzzle_number": 1,
                "resolve_time": float(i),
                "browser_uuid": f"u{i}",
                "timestamp_utc": "2026-03-18T10:00:00Z",
            }
            for i in range(1, 11)
        ],
    )
    resp = client.get("/octile/scoreboard?limit=3&offset=0")
    data = resp.json()
    assert data["total"] == 10
    assert len(data["scores"]) == 3
    assert data["scores"][0]["resolve_time"] == 1.0

    resp2 = client.get("/octile/scoreboard?limit=3&offset=3")
    data2 = resp2.json()
    assert len(data2["scores"]) == 3
    assert data2["scores"][0]["resolve_time"] == 4.0


# ---------------------------------------------------------------------------
# GET /octile/puzzles
# ---------------------------------------------------------------------------


def test_puzzles_endpoint(client):
    _insert_scores(
        client,
        [
            {
                "puzzle_number": 1,
                "resolve_time": 10.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:00:00Z",
            },
            {
                "puzzle_number": 1,
                "resolve_time": 5.0,
                "browser_uuid": "u2",
                "timestamp_utc": "2026-03-18T10:01:00Z",
            },
            {
                "puzzle_number": 2,
                "resolve_time": 20.0,
                "browser_uuid": "u1",
                "timestamp_utc": "2026-03-18T10:02:00Z",
            },
        ],
    )
    resp = client.get("/octile/puzzles")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    p1 = data[0]
    assert p1["puzzle_number"] == 1
    assert p1["total_scores"] == 2
    assert p1["unique_players"] == 2
    assert p1["best_time"] == 5.0

    p2 = data[1]
    assert p2["puzzle_number"] == 2
    assert p2["total_scores"] == 1
    assert p2["unique_players"] == 1
    assert p2["best_time"] == 20.0


def test_puzzles_empty(client):
    resp = client.get("/octile/puzzles")
    assert resp.status_code == 200
    assert resp.json() == []
