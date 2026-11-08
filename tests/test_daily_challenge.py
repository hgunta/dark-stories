"""Daily Mystery MVP: UTC rotation, scoring, privacy, solo resume contract."""
from datetime import date, timedelta
import json
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from backend.daily import challenge_for, daily_score


@pytest.fixture
def daily_clock(isolated_app, monkeypatch):
    day = [date(2026, 11, 7)]
    monkeypatch.setattr(isolated_app, "utc_today", lambda: day[0])
    return day


def start(client):
    response = client.post("/api/daily/start")
    assert response.status_code == 200
    return response.json()


def result(client, room):
    return client.get(f"/api/daily/result/{room['room_id']}")


def test_same_utc_date_yields_same_case_across_clients(client, isolated_app, daily_clock):
    with TestClient(isolated_app.app) as guest:
        a = client.get("/api/daily")
        b = guest.get("/api/daily")
        assert a.status_code == b.status_code == 200
        assert a.json() == b.json()
        assert a.json()["date"] == "2026-11-07"
        assert a.json()["reset_timezone"] == "UTC"
        assert set(a.json()) == {"date", "mystery_id", "title", "reset_timezone"}
        assert "solution_summary" not in json.dumps(a.json())
        assert "facts" not in json.dumps(a.json())


def test_utc_rotation_is_deterministic_and_catalog_order_independent():
    entries = [{"id": "ms-003", "title": "C"}, {"id": "ms-001", "title": "A"}, {"id": "ms-002", "title": "B"}]
    base = date(2026, 11, 1)
    seq = [challenge_for(base + timedelta(days=i), entries)["mystery_id"] for i in range(6)]
    assert seq == ["ms-001", "ms-002", "ms-003"] * 2
    assert challenge_for(base - timedelta(days=1), entries)["mystery_id"] == "ms-003"
    assert seq == [challenge_for(base + timedelta(days=i), list(reversed(entries)))["mystery_id"] for i in range(6)]
    with pytest.raises(ValueError):
        challenge_for(base, [])


def test_next_utc_day_changes_mystery(client, daily_clock):
    first = client.get("/api/daily").json()
    daily_clock[0] += timedelta(days=1)
    second = client.get("/api/daily").json()
    assert first["date"] != second["date"]
    assert first["mystery_id"] != second["mystery_id"]


def test_daily_start_uses_server_selection_not_caller_mystery(client, isolated_app, daily_clock):
    metadata = client.get("/api/daily").json()
    game = start(client)
    assert isolated_app.ROOMS[game["room_id"]]["mystery"]["mystery_id"] == metadata["mystery_id"]
    assert set(game) == {"room_id", "room_code", "premise", "title"}
    r = result(client, game)
    assert r.status_code == 200
    assert r.json() == {
        "date": metadata["date"], "mystery_id": metadata["mystery_id"], "completed": False,
        "outcome": None, "questions": 0, "hints": 0, "wrong_guesses": 0, "score": None,
    }
    # Dedicated endpoint has no request body or client-chosen mystery ID.
    assert client.post("/api/daily/start", json={"mystery_id": "ms-003"}).status_code == 200


def test_daily_score_rules():
    assert daily_score(solved=True, revealed=False, questions=0, hints=0, wrong_guesses=0) == 100
    assert daily_score(solved=True, revealed=False, questions=3, hints=1, wrong_guesses=2) == 50
    assert daily_score(solved=True, revealed=False, questions=100, hints=10, wrong_guesses=10) == 10
    assert daily_score(solved=True, revealed=True, questions=0, hints=0, wrong_guesses=0) == 0
    assert daily_score(solved=False, revealed=False, questions=0, hints=0, wrong_guesses=0) == 0


def test_question_hint_wrong_guess_then_private_solve_scored(client, moderator, daily_clock):
    room = start(client)
    moderator("No")
    response = client.post("/api/message", json={"room_id": room["room_id"], "text": "Was it a crime?"})
    assert response.status_code == 200
    hint = client.post("/api/hint", json={"room_id": room["room_id"], "text": "/hint"})
    assert hint.status_code == 200
    moderator("No")
    wrong = client.post("/api/private_guess", json={"room_id": room["room_id"], "guess": "PRIVATE WRONG GUESS"})
    assert wrong.json()["correct"] is False
    moderator("Solved")
    solved = client.post("/api/private_guess", json={"room_id": room["room_id"], "guess": "PRIVATE RIGHT GUESS"})
    assert solved.json()["correct"] is True
    stats = result(client, room).json()
    assert stats["completed"] is True
    assert stats["outcome"] == "solved"
    assert stats["questions"] == 1
    assert stats["hints"] == 1
    assert stats["wrong_guesses"] == 1
    assert stats["score"] == 70
    assert "PRIVATE" not in json.dumps(stats)
    public = client.get(f"/api/room_state/{room['room_code']}").json()
    assert "PRIVATE" not in json.dumps(public)


def test_normal_ai_solve_scored_as_completed(client, moderator):
    room = start(client)
    moderator("Solved")
    response = client.post("/api/message", json={"room_id": room["room_id"], "text": "I think they were fish."})
    assert response.json()["solved"] is True
    stats = result(client, room).json()
    assert stats["outcome"] == "solved"
    assert stats["questions"] == 1
    assert stats["score"] == 95


def test_reveal_gives_no_solve_score(client):
    room = start(client)
    hint = client.post("/api/hint", json={"room_id": room["room_id"], "text": "/hint"})
    assert hint.status_code == 200
    assert client.post("/api/reveal", json={"room_id":room["room_id"], "text":"/reveal"}).status_code == 200
    stats = result(client, room).json()
    assert stats["outcome"] == "revealed"
    assert stats["score"] == 0
    assert stats["hints"] == 1


def test_free_play_room_has_no_daily_result(client, create_room):
    room = create_room()
    assert result(client, room).status_code == 404


def test_unknown_daily_result_and_expiry(client, isolated_app, monkeypatch):
    clock = [1000.]
    monkeypatch.setattr(isolated_app.time, "monotonic", lambda: clock[0])
    room = start(client)
    assert client.get("/api/daily/result/not-a-room").status_code == 404
    clock[0] += isolated_app.ROOM_IDLE_SECONDS
    assert result(client, room).status_code == 404


def test_failed_ai_question_is_not_charged_for_score(client, moderator):
    room = start(client)
    completion = moderator("No")
    completion.side_effect = RuntimeError("private upstream error")
    answer = client.post("/api/message", json={"room_id": room["room_id"], "text": "Question"})
    assert answer.status_code == 503
    assert result(client, room).json()["questions"] == 0


def test_daily_ui_defaults_to_daily_and_preserves_free_play():
    html = (Path(__file__).resolve().parents[1] / "frontend/index.html").read_text(encoding="utf-8")
    for snippet in (
        'id="daily-start"', 'id="daily-share"', 'id="daily-result"',
        "async function startDaily()", "async function loadDailyChallenge()",
        "async function refreshDailyResult()", "localStorage.setItem(DAILY_SESSION_KEY",
        "if (invitedCode) await joinRoom(invitedCode)",
        "else if (params.has('daily') || !params.has('free')) await startDaily()",
        "else await createRoom(CURRENT_MYSTERY)",
        "shareDailyResult()", "/?daily=1",
        "setRoomDisplay(prior.room_code)",
    ):
        assert snippet in html
    assert "body.daily-active .invite-bar" in html
    assert "result.questions" in html
