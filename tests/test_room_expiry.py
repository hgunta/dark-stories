"""Deterministic inactive-room expiry and cleanup: no background worker or sleeps."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def clock(isolated_app, monkeypatch):
    ticks = [1000.0]
    monkeypatch.setattr(isolated_app, "time", SimpleNamespace(monotonic=lambda: ticks[0]))
    return ticks


def message(client, room):
    return client.post("/api/message", json={"room_id": room["room_id"], "text": "/premise"})


def test_rooms_expire_at_exact_idle_boundary_and_release_codes(client, create_room, isolated_app, clock):
    room = create_room()
    assert room["room_id"] in isolated_app.ROOMS
    assert room["room_code"] in isolated_app.CODE_MAP
    clock[0] += isolated_app.ROOM_IDLE_SECONDS - 0.001
    assert message(client, room).status_code == 200
    clock[0] += isolated_app.ROOM_IDLE_SECONDS - 0.001
    assert client.get(f"/api/join/{room['room_code']}").status_code == 200
    clock[0] += isolated_app.ROOM_IDLE_SECONDS
    assert message(client, room).status_code == 404
    assert room["room_id"] not in isolated_app.ROOMS
    assert room["room_code"] not in isolated_app.CODE_MAP
    assert client.get(f"/api/join/{room['room_code']}").status_code == 404


def test_activity_in_one_room_does_not_keep_another_alive(client, create_room, isolated_app, clock):
    a = create_room()
    clock[0] += 10
    b = create_room("ms-002")
    clock[0] += isolated_app.ROOM_IDLE_SECONDS - 5
    assert message(client, b).status_code == 200
    assert a["room_id"] not in isolated_app.ROOMS
    assert b["room_id"] in isolated_app.ROOMS
    assert a["room_code"] not in isolated_app.CODE_MAP


def test_new_room_triggers_lazy_expiry_cleanup_without_background_task(client, create_room, isolated_app, clock):
    old = create_room()
    clock[0] += isolated_app.ROOM_IDLE_SECONDS
    fresh = create_room("ms-003")
    assert old["room_id"] not in isolated_app.ROOMS
    assert old["room_code"] not in isolated_app.CODE_MAP
    assert fresh["room_id"] in isolated_app.ROOMS


@pytest.mark.parametrize("route,method,body", [
    ("/api/message", "post", {"text": "Question?"}),
    ("/api/hint", "post", {"text": "/hint"}),
    ("/api/reveal", "post", {"text": "/reveal"}),
    ("/api/feedback", "post", {"rating": 5}),
])
def test_expired_rooms_rejected_across_actions(client, create_room, isolated_app, clock, route, method, body):
    room = create_room()
    if route == "/api/feedback":
        result = client.post("/api/reveal", json={"room_id": room["room_id"], "text": "/reveal"})
        assert result.status_code == 200
    clock[0] += isolated_app.ROOM_IDLE_SECONDS
    response = getattr(client, method)(route, json={"room_id": room["room_id"], **body})
    assert response.status_code == 404
    assert response.json() == {"detail": "Room not found"}


def test_fallback_room_code_resolves_live_room_and_touch_refreshes_activity(
    client, create_room, isolated_app, clock
):
    a, b = create_room(), create_room("ms-002")
    clock[0] += isolated_app.ROOM_IDLE_SECONDS - 1
    result = client.post("/api/message", json={
        "room_id": "missing", "room_code": b["room_code"].lower(), "text": "/premise"})
    assert result.status_code == 200
    clock[0] += 2
    # Cleanup is request-driven; the next request triggers eviction.
    assert message(client, b).status_code == 200
    assert a["room_id"] not in isolated_app.ROOMS
    assert b["room_id"] in isolated_app.ROOMS


def test_known_room_does_not_leak_into_new_game_when_old_room_expired(client, create_room, clock):
    old = create_room()
    clock[0] += 7200
    assert message(client, old).status_code == 404
    newer = create_room()
    assert newer["room_id"] != old["room_id"]
    assert message(client, newer).status_code == 200


def test_browser_explains_expired_or_missing_room():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "frontend/index.html").read_text()
    assert "This game is no longer available. Start a new game." in html
    assert "missingRoom" in html
