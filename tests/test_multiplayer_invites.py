"""Multiplayer first slice: invite/join and bounded spoiler-safe shared activity."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.multiplayer import append_public, public_snapshot, MAX_PUBLIC_EVENTS


def snapshot(client, code):
    return client.get(f"/api/room_state/{code}")


def test_two_browser_clients_share_question_and_reply(client, create_room, moderator, isolated_app):
    room = create_room("ms-002")
    with TestClient(isolated_app.app) as guest:
        joined = guest.get(f"/api/join/{room['room_code'].lower()}")
        assert joined.status_code == 200
        assert joined.json()["room_id"] == room["room_id"]
        moderator("Yes")
        response = guest.post("/api/message", json={
            "room_id": joined.json()["room_id"], "text": "Was anyone injured?"
        })
        assert response.status_code == 200
        assert response.json()["reply"] == "Yes"
        shared = snapshot(client, room["room_code"])
        assert shared.status_code == 200
        data = shared.json()
        assert data["room_code"] == room["room_code"]
        assert data["mystery_id"] == "ms-002"
        assert data["events"] == [{
            "seq": 1, "kind": "question", "question": "Was anyone injured?", "reply": "Yes",
        }]
        assert data["last_seq"] == 1
        assert snapshot(guest, room["room_code"]).json() == data


def test_public_hints_are_in_order_for_both_clients(client, create_room, isolated_app):
    room = create_room()
    with TestClient(isolated_app.app) as guest:
        guest.post("/api/hint", json={"room_id": room["room_id"], "text": "/hint"})
        first = snapshot(client, room["room_code"]).json()
        assert first["hints_used"] == 1
        assert first["events"][0]["kind"] == "hint"
        assert first["events"][0]["reply"].startswith("Hint 1:")
        client.post("/api/hint", json={"room_id": room["room_id"], "text": "/hint"})
        second = snapshot(guest, room["room_code"]).json()
        assert second["hints_used"] == 2
        assert [e["seq"] for e in second["events"]] == [1, 2]


def test_public_snapshot_never_reveals_private_solution(client, create_room, mystery):
    room = create_room()
    secret = mystery("ms-001")["solution_summary"]
    response = client.post("/api/reveal", json={"room_id": room["room_id"], "text": "/reveal"})
    assert secret in response.json()["reply"]
    data = snapshot(client, room["room_code"]).json()
    assert data["solved"] is True
    assert data["events"] == [{"seq": 1, "kind": "revealed"}]
    assert secret not in json.dumps(data)
    assert "acceptable_solutions" not in json.dumps(data)
    assert "forbidden_reveals" not in json.dumps(data)


def test_auto_solved_guess_is_not_exposed_to_other_players(client, create_room, moderator, mystery):
    room = create_room()
    moderator("Solved")
    secret_text = "MY_PRIVATE_SOLVED_GUESS"
    solved = client.post("/api/message", json={
        "room_id": room["room_id"], "text": secret_text,
    })
    assert solved.json()["solved"] is True
    visible = snapshot(client, room["room_code"]).json()
    assert visible["events"] == [{"seq": 1, "kind": "solved"}]
    assert secret_text not in json.dumps(visible)
    assert mystery("ms-001")["solution_summary"] not in json.dumps(visible)


def test_read_only_poll_does_not_extend_idle_expiry(client, create_room, isolated_app, monkeypatch):
    ticks = [1000.]
    monkeypatch.setattr(isolated_app.time, "monotonic", lambda: ticks[0])
    room = create_room()
    for moment in [1010., 4000., 8199.]:
        ticks[0] = moment
        assert snapshot(client, room["room_code"]).status_code == 200
    ticks[0] = 8200.
    assert snapshot(client, room["room_code"]).status_code == 404
    assert room["room_code"] not in isolated_app.CODE_MAP


def test_unknown_room_snapshot_has_generic_404(client):
    missing = snapshot(client, "ZZZZ")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Room not found"}


def test_bounded_feed_and_incrementing_sequence():
    room = {
        "code": "ABCD",
        "mystery": {"mystery_id": "ms-001", "title": "Test", "premise_public": "Public"},
        "state": {"solved": False, "hints_used": 0},
    }
    for i in range(MAX_PUBLIC_EVENTS + 15):
        append_public(room, "question", question="a" * 500, reply="Yes")
    view = public_snapshot(room)
    assert len(view["events"]) == MAX_PUBLIC_EVENTS
    assert view["events"][0]["seq"] == 16
    assert view["events"][-1]["seq"] == MAX_PUBLIC_EVENTS + 15
    assert len(view["events"][0]["question"]) == 400


def test_snapshot_is_not_live_mutable_reference():
    room = {
        "code": "ABCD",
        "mystery": {"mystery_id": "ms-001", "title": "Test", "premise_public": "Public"},
        "state": {"solved": False, "hints_used": 0},
    }
    append_public(room, "question", question="Safe?", reply="Yes")
    snap = public_snapshot(room)
    snap["events"][0]["question"] = "tampered"
    assert room["public_events"][0]["question"] == "Safe?"


def test_frontend_invite_and_polling_flow():
    page = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text()
    for value in (
        'id="join-code"', 'id="join-room"', 'id="room-share"',
        'id="public-events"', "async function joinRoom(code)",
        "async function refreshPublicFeed()", "setInterval(refreshPublicFeed, 3000)",
        "new URLSearchParams(location.search).get('room')",
        "document.createElement('div')", "div.textContent =",
        "Private solution guesses are not yet supported.",
    ):
        assert value in page
