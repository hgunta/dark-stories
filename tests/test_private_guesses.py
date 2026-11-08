"""DS Phase 2B: private guesses never enter public room snapshots or logs."""
import json
from pathlib import Path
from types import SimpleNamespace
from fastapi.testclient import TestClient
import pytest


def guess(client, room, text="The fishbowl broke"):
    return client.post("/api/private_guess", json={
        "room_id": room["room_id"], "guess": text,
    })


def snapshot(client, room):
    return client.get(f"/api/room_state/{room['room_code']}").json()


def test_incorrect_guess_response_private_between_two_clients(
    client, create_room, moderator, isolated_app
):
    room = create_room()
    completion = moderator("No", nudge="PRIVATE_SENTINEL_HINT")
    secret = "MY_PRIVATE_WRONG_GUESS_SENTINEL"
    with TestClient(isolated_app.app) as guest:
        response = guess(client, room, secret)
        assert response.status_code == 200
        assert response.json() == {
            "correct": False, "solved": False, "reply": "Not quite. Keep investigating.",
        }
        assert completion.call_count == 1
        call = completion.call_args.kwargs
        assert call["messages"][1]["content"] == secret
        assert "PRIVATE_SENTINEL_HINT" not in response.text
        assert secret not in json.dumps(snapshot(guest, room))
        assert snapshot(guest, room)["events"] == []
        assert isolated_app.ROOMS[room["room_id"]]["state"]["confirmed_true"] == set()
        assert isolated_app.ROOMS[room["room_id"]]["state"]["asked"] == 0


def test_correct_guess_ends_shared_room_without_leaking_guess_or_solution(
    client, create_room, moderator, isolated_app, mystery
):
    room = create_room()
    moderator("Solved")
    secret = "PRIVATE_CORRECT_SENTINEL"
    with TestClient(isolated_app.app) as guest:
        response = guess(client, room, secret)
        assert response.status_code == 200
        assert response.json()["correct"] is True
        assert response.json()["solved"] is True
        public = snapshot(guest, room)
        assert public["solved"] is True
        assert public["events"] == [{"seq": 1, "kind": "solved"}]
        assert secret not in json.dumps(public)
        assert mystery("ms-001")["solution_summary"] not in json.dumps(public)
        assert guess(guest, room, "my second attempt").status_code == 409


def test_private_guess_error_is_sanitized_no_public_activity(
    client, create_room, moderator
):
    room = create_room()
    completion = moderator()
    completion.side_effect = RuntimeError("SECRET_UPSTREAM_TEXT")
    response = guess(client, room, "MY_SECRET_GUESS")
    assert response.status_code == 503
    assert response.json() == {"detail": "Could not check your guess. Please retry."}
    assert "SECRET" not in response.text
    assert snapshot(client, room)["events"] == []


def test_private_guess_validation_and_unknown_room(client, create_room):
    room = create_room()
    assert guess(client, {"room_id": "missing"}).status_code == 404
    assert guess(client, room, " ").status_code == 422
    for payload in [
        {"room_id": room["room_id"], "guess": ""},
        {"room_id": room["room_id"], "guess": "x" * 1001},
        {"room_id": room["room_id"], "guess": "hi", "participant_id": "faked"},
        {"room_id": room["room_id"], "guess": "hi", "text": "SHOULD_NOT_LOG"},
    ]:
        assert client.post("/api/private_guess", json=payload).status_code == 422
    assert snapshot(client, room)["events"] == []


def test_offline_preview_exactish_match_without_ai(client, create_room, mystery, isolated_app):
    room = create_room()
    expected = mystery("ms-001")["acceptable_solutions"][0]
    response = guess(client, room, expected)
    assert response.status_code == 200
    assert response.json()["correct"] is True
    assert snapshot(client, room)["events"] == [{"seq": 1, "kind": "solved"}]


def test_wrong_guess_does_not_mark_solved_offline(client, create_room):
    room = create_room()
    result = guess(client, room, "I have no idea")
    assert result.status_code == 200
    assert result.json()["correct"] is False
    assert snapshot(client, room)["solved"] is False


def test_share_rate_limits_with_public_ai_questions(
    client, create_room, moderator, isolated_app
):
    room = create_room()
    limiter = isolated_app.request_limiter
    limiter.QUESTIONS_PER_ROOM_PER_MINUTE = 1
    moderator("No")
    assert guess(client, room, "private first").status_code == 200
    denied = guess(client, room, "private second")
    assert denied.status_code == 429
    assert denied.headers["retry-after"].isdigit()
    assert denied.json()["detail"] == "Too many questions. Please try again shortly."
    assert snapshot(client, room)["events"] == []


def test_private_guesses_not_appended_public_even_as_nudges(
    client, create_room, moderator
):
    room = create_room()
    moderator("No", nudge="my private hint")
    assert guess(client, room, "PRIVATE_TEXT").status_code == 200
    assert snapshot(client, room)["events"] == []


def test_private_ui_is_separate_from_public_chat():
    html = (Path(__file__).resolve().parents[1] / "frontend/index.html").read_text()
    for phrase in (
        'id="private-guess-form"', 'id="private-guess-input"',
        'id="private-guess-result"', "async function submitPrivateGuess(event)",
        "body:JSON.stringify({room_id:roomId, guess})",
        "el('private-guess-input').value = ''",
        "Private solution guesses are not yet supported.",
    ):
        if phrase == "Private solution guesses are not yet supported.":
            assert phrase not in html
        else:
            assert phrase in html
    assert "el('private-guess-form')?.addEventListener('submit', submitPrivateGuess)" in html
