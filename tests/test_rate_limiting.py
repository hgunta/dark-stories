"""DS-010C: deterministic request admission, API contracts, and no-PII regression."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.rate_limit import RequestLimiter


@pytest.fixture
def limits(isolated_app, monkeypatch):
    ticks = [10_000.0]
    limiter = RequestLimiter(clock=lambda: ticks[0])
    monkeypatch.setattr(isolated_app, "request_limiter", limiter)
    return limiter, ticks


def post_question(client, room, text="Was it an accident?"):
    return client.post("/api/message", json={"room_id": room["room_id"], "text": text})


def test_limiter_boundary_and_exact_retry_after(limits):
    limiter, ticks = limits
    limiter.ROOM_CREATES_PER_MINUTE = 2
    assert limiter.allow_create() == (True, 0)
    assert limiter.allow_create() == (True, 0)
    assert limiter.allow_create() == (False, 60)
    ticks[0] += 59.01
    assert limiter.allow_create() == (False, 1)
    ticks[0] += 0.99
    assert limiter.allow_create() == (True, 0)


def test_global_and_per_room_buckets_admitted_atomically(limits):
    limiter, _ = limits
    limiter.QUESTIONS_PER_ROOM_PER_MINUTE = 2
    limiter.QUESTIONS_GLOBAL_PER_MINUTE = 3
    assert limiter.allow_question("one") == (True, 0)
    assert limiter.allow_question("one") == (True, 0)
    assert limiter.allow_question("one") == (False, 60)
    assert limiter.allow_question("two") == (True, 0)
    assert limiter.allow_question("two") == (False, 60)
    assert len(limiter._buckets["questions_global"]) == 3
    assert len(limiter._buckets[("question_room", "one")]) == 2
    assert len(limiter._buckets[("question_room", "two")]) == 1


def test_limiter_removes_idle_keys_without_background_jobs(limits):
    limiter, ticks = limits
    for index in range(30):
        assert limiter.allow_question(str(index))[0]
    assert len(limiter._buckets) == 31
    ticks[0] += 60
    assert limiter.allow_create() == (True, 0)
    assert set(limiter._buckets) == {"create"}


def test_parallel_admission_has_exact_quota(limits):
    limiter, _ = limits
    limiter.ROOM_CREATES_PER_MINUTE = 6
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(lambda _: limiter.allow_create()[0], range(24)))
    assert outcomes.count(True) == 6
    assert outcomes.count(False) == 18


def test_room_creation_limit_returns_429_without_creating_extra_rooms(client, isolated_app, limits):
    limiter, ticks = limits
    limiter.ROOM_CREATES_PER_MINUTE = 2
    ids = [client.post("/api/create_room", json={"mystery_id": "ms-001"}) for _ in range(3)]
    assert [r.status_code for r in ids] == [200, 200, 429]
    assert ids[-1].json() == {"detail": "Too many new games. Please try again shortly."}
    assert ids[-1].headers["retry-after"] == "60"
    assert len(isolated_app.ROOMS) == 2
    ticks[0] += 60
    assert client.post("/api/create_room", json={}).status_code == 200


def test_per_room_limit_denies_without_calling_paid_moderator(
    client, create_room, moderator, limits, isolated_app
):
    limiter, ticks = limits
    limiter.QUESTIONS_PER_ROOM_PER_MINUTE = 2
    limiter.QUESTIONS_GLOBAL_PER_MINUTE = 100
    room = create_room()
    completion = moderator("No")
    assert post_question(client, room).status_code == 200
    assert post_question(client, room).status_code == 200
    denied = post_question(client, room)
    assert denied.status_code == 429
    assert denied.headers["retry-after"] == "60"
    assert denied.json()["detail"] == "Too many questions. Please try again shortly."
    assert completion.call_count == 2
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is False
    # Local help requests and hints/reveals remain usable under a question cap.
    assert post_question(client, room, "/help").status_code == 200
    assert client.post("/api/hint", json={"room_id": room["room_id"], "text": "/hint"}).status_code == 200
    ticks[0] += 60
    assert post_question(client, room).status_code == 200
    assert completion.call_count == 3


def test_global_limit_applies_across_rooms(client, create_room, moderator, limits):
    limiter, _ = limits
    limiter.QUESTIONS_PER_ROOM_PER_MINUTE = 10
    limiter.QUESTIONS_GLOBAL_PER_MINUTE = 2
    a, b = create_room(), create_room("ms-002")
    completion = moderator("No")
    assert post_question(client, a).status_code == 200
    assert post_question(client, b).status_code == 200
    assert post_question(client, a).status_code == 429
    assert completion.call_count == 2


def test_invalid_room_and_finished_game_are_not_rate_limited(client, create_room, limits):
    limiter, _ = limits
    limiter.QUESTIONS_PER_ROOM_PER_MINUTE = 1
    room = create_room()
    assert post_question(client, room).status_code == 200
    assert post_question(client, {"room_id": "missing"}).status_code == 404
    assert client.post("/api/reveal", json={
        "room_id": room["room_id"], "text": "/reveal"}).status_code == 200
    finished = post_question(client, room)
    assert finished.status_code == 200
    assert finished.json()["solved"] is True


def test_no_ip_raw_question_or_client_fingerprint_tracking(limits):
    limiter, _ = limits
    limiter.allow_create()
    limiter.allow_question("room-123")
    assert all(isinstance(key, (str, tuple)) for key in limiter._buckets)
    assert set(limiter._buckets) == {"create", "questions_global", ("question_room", "room-123")}
    assert not hasattr(limiter, "client_ip")
    assert not hasattr(limiter, "user_agent")
    assert not hasattr(limiter, "prompt")


def test_ui_shows_user_friendly_429_retry_message():
    html = (Path(__file__).resolve().parents[1] / "frontend/index.html").read_text()
    assert "error.message.startsWith('429 ')" in html
    assert "Too many requests right now. Please wait about a minute, then try again." in html
    assert "if (!el('input').value.trim()) el('input').value = text;" in html
