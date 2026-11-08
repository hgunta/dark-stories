"""Opt-in local instrumentation with fake clock/IDs and explicit temporary store."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib
import itertools
import json
from unittest.mock import Mock
from uuid import UUID

import pytest


@pytest.fixture
def recording(isolated_app, monkeypatch, tmp_path):
    storage = importlib.import_module("analytics_storage")
    store = storage.SQLiteEventStore(tmp_path / "events.sqlite3")
    store.initialize()
    numbers = itertools.count(1)
    recorder = isolated_app.AnalyticsRecorder(
        store, enabled=True, environment="test",
        clock=lambda: datetime(2026, 11, 7, 12, 30, tzinfo=timezone.utc),
        id_factory=lambda: UUID(int=next(numbers), version=4),
    )
    monkeypatch.setattr(isolated_app, "analytics_recorder", recorder)
    return recorder, store


def rows(recording):
    return recording[1].read(environment="test", limit=1000)


def names(recording):
    return [e.event_name for e in rows(recording)]


def post(client, room, endpoint="message", text="Was it an accident?"):
    return client.post(f"/api/{endpoint}", json={"room_id": room["room_id"], "text": text})


def test_normal_startup_is_disabled_even_with_environment_flags(isolated_app, monkeypatch, tmp_path, client, create_room):
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("ANALYTICS_DATABASE_PATH", str(tmp_path / "should-not-exist.sqlite3"))
    disabled = isolated_app.analytics_recorder
    assert disabled.enabled is False
    assert disabled.store is None
    assert disabled._games == {}
    room = create_room()
    assert post(client, room).json() == {"reply": "Unknown. (offline mode)", "solved": False}
    assert post(client, room, "reveal").json()["solved"] is True
    assert disabled._games == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("environment", [None, "production", "staging", "unknown"])
def test_no_production_or_implicit_activation(isolated_app, environment):
    with pytest.raises(ValueError):
        isolated_app.AnalyticsRecorder(Mock(), enabled=True, environment=environment)
    with pytest.raises(ValueError):
        isolated_app.AnalyticsRecorder(enabled=True, environment="test")


def test_enabled_offline_event_sequence_and_hint_exhaustion(recording, client, create_room):
    room = create_room()
    assert post(client, room).json() == {"reply": "Unknown. (offline mode)", "solved": False}
    for _ in range(3):
        post(client, room, "hint")
    post(client, room, "reveal")
    post(client, room, "reveal")
    post(client, room)  # game-over is not another ordinary question
    assert names(recording) == [
        "game_started", "question_submitted", "question_answered",
        "hint_requested", "hint_delivered", "hint_requested", "hint_delivered", "hint_requested",
        "solution_revealed", "solution_revealed",
    ]
    events = rows(recording)
    assert [e.game_sequence for e in events] == list(range(1, 11))
    assert len({e.event_id for e in events}) == len(events)
    assert len({e.game_session_id for e in events}) == 1
    assert all(e.mode == "offline" and e.browser_visit_id is None for e in events)
    assert events[1].properties.attempt_id == events[2].properties.attempt_id
    assert events[2].properties.response_origin == "offline_stub"
    assert events[2].properties.response_category == "unknown"
    assert [e.properties.establishes_outcome for e in events if e.event_name == "solution_revealed"] == [True, False]
    assert recording[0].dropped == 0


@pytest.mark.parametrize("command", ["/help", "/rules", "/premise", " /HELP "])
def test_control_commands_are_not_questions(recording, client, create_room, command):
    room = create_room()
    assert post(client, room, text=command).status_code == 200
    assert names(recording) == ["game_started"]


@pytest.mark.parametrize("label,category", [("Yes", "yes"), ("No", "no"), ("Unknown", "unknown"),
                                         ("Irrelevant", "irrelevant"), ("AskYesNo", "ask_yes_no"),
                                         ("unexpected", "unknown")])
def test_mocked_ai_response_categories(recording, client, create_room, moderator, label, category):
    room = create_room()
    moderator(label)
    assert post(client, room).status_code == 200
    answer = rows(recording)[-1]
    assert answer.event_name == "question_answered"
    assert answer.mode == "ai"
    assert answer.properties.response_origin == "ai_tool"
    assert answer.properties.response_category == category
    assert recording[0].dropped == 0


def test_ai_fallback_is_not_tool_response(recording, client, create_room, moderator):
    room = create_room()
    completion = moderator()
    completion.return_value.choices[0].message.tool_calls = []
    assert post(client, room).json() == {"reply": "Unknown", "solved": False}
    assert rows(recording)[-1].properties.response_origin == "ai_fallback"


@pytest.mark.parametrize("method", ["required_facts", "moderator_label"])
def test_solve_distinct_from_reveal_and_no_duplicate_terminal(recording, client, create_room, moderator, method):
    room = create_room()
    moderator("Yes", indices=[0, 1, 2]) if method == "required_facts" else moderator("Solved")
    assert post(client, room).json()["solved"] is True
    post(client, room)  # same completed game cannot generate a second solve
    post(client, room, "reveal")
    events = rows(recording)
    assert [e.event_name for e in events] == ["game_started", "question_submitted", "question_answered", "game_solved", "solution_revealed"]
    assert events[2].properties.response_category == "solved"
    assert events[3].properties.solve_method == method
    assert events[1].properties.attempt_id == events[2].properties.attempt_id == events[3].properties.attempt_id
    assert events[4].properties.establishes_outcome is False
    assert recording[0].dropped == 0


def test_hints_after_end_remain_allowed_but_marked_post_terminal(recording, client, create_room):
    room = create_room()
    post(client, room, "reveal")
    assert post(client, room, "hint").json()["reply"].startswith("Hint 1:")
    events = rows(recording)
    assert events[-2].properties.pre_terminal is False
    assert events[-1].properties.pre_terminal is False


def test_multiple_rooms_have_separate_ids_sequences_and_outcomes(recording, client, create_room):
    first, second = create_room(), create_room("ms-002")
    post(client, first)
    post(client, second, "hint")
    post(client, first, "reveal")
    events = rows(recording)
    starts = [e for e in events if e.event_name == "game_started"]
    assert starts[0].game_session_id != starts[1].game_session_id
    assert {e.mystery_id for e in events} == {"ms-001", "ms-002"}
    for start in starts:
        per_game = recording[1].read(environment="test", game_session_id=start.game_session_id)
        assert [e.game_sequence for e in per_game] == list(range(1, len(per_game) + 1))
    assert post(client, second).json()["solved"] is False


@pytest.mark.parametrize("operation,path,body", [
    ("message", "/api/message", {"room_id": "missing", "text": "PRIVATE_SENTINEL"}),
    ("hint", "/api/hint", {"room_id": "missing", "text": "/hint"}),
    ("reveal", "/api/reveal", {"room_id": "missing", "text": "/reveal"}),
    ("join", "/api/join/ZZZZ", None),
])
def test_unknown_room_errors_preserve_404(recording, client, operation, path, body):
    response = client.get(path) if body is None else client.post(path, json=body)
    assert response.status_code == 404
    assert response.json() == {"detail": "Room not found"}
    events = rows(recording)
    assert len(events) == 1
    error = events[0]
    assert error.event_name == "game_error"
    assert error.properties.operation == operation
    assert error.properties.error_code == "unknown_room"
    assert error.game_session_id is None and error.mystery_id is None


@pytest.mark.parametrize("path", ["/api/create_room", "/api/message", "/api/hint", "/api/reveal"])
def test_invalid_request_errors_preserve_422(recording, client, path):
    # create requires a request body; message/hint/reveal also require text.
    response = client.post(path)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert names(recording) == ["game_error"]
    assert rows(recording)[0].properties.error_code == "invalid_request"


def test_missing_mystery_error_returns_404(recording, client):
    response = client.post("/api/create_room", json={"mystery_id": "missing"})
    assert response.status_code == 404
    assert names(recording) == ["game_error"]
    assert rows(recording)[0].properties.error_code == "unknown_mystery"
    assert rows(recording)[0].mystery_id is None


@pytest.mark.parametrize("failure", ["json", "upstream"])
def test_classifier_errors_correlate_to_question_without_answer(recording, client, create_room, moderator, failure, caplog):
    room = create_room()
    completion = moderator()
    if failure == "json":
        completion.return_value.choices[0].message.tool_calls[0].function.arguments = "PRIVATE_SENTINEL"
        code = "invalid_ai_output"
    else:
        completion.side_effect = RuntimeError("PRIVATE_SENTINEL")
        code = "ai_failure"
    response = post(client, room, text="PRIVATE_SENTINEL")
    assert response.status_code == 503
    assert response.json() == {"detail": "The moderator is unavailable. Please try again."}
    assert "PRIVATE_SENTINEL" not in response.text
    events = rows(recording)
    assert [e.event_name for e in events] == ["game_started", "question_submitted", "game_error"]
    assert events[-1].properties.attempt_id == events[-2].properties.attempt_id
    assert events[-1].properties.error_code == code
    assert "PRIVATE_SENTINEL" not in caplog.text
    assert "PRIVATE_SENTINEL" not in "".join(e.model_dump_json() for e in events)


def test_events_never_contain_private_game_content(recording, client, create_room, moderator, mystery):
    room = create_room()
    moderator("Yes", nudge="PRIVATE_SENTINEL")
    post(client, room, text="PRIVATE_QUESTION")
    post(client, room, "hint")
    post(client, room, "reveal")
    serialized = "".join(e.model_dump_json() for e in rows(recording))
    forbidden = ["PRIVATE_QUESTION", "PRIVATE_SENTINEL", mystery("ms-001")["solution_summary"],
                 *mystery("ms-001")["hints"], *[f["text"] for f in mystery("ms-001")["facts"]]]
    assert all(value not in serialized for value in forbidden)
    assert room["room_id"] not in {str(e.game_session_id) for e in rows(recording)}


def test_noop_repeat_start_and_concurrent_terminal_callbacks(recording, client, create_room, isolated_app):
    room = create_room()
    internal = isolated_app.ROOMS[room["room_id"]]
    recorder, _ = recording
    recorder.start(internal, "offline")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: recorder.revealed(internal, "offline", False), range(2)))
    events = rows(recording)
    assert [e.event_name for e in events] == ["game_started", "solution_revealed", "solution_revealed"]
    assert [e.properties.establishes_outcome for e in events[1:]] == [True, False]
    assert recorder.dropped == 0


@pytest.mark.parametrize("failure_point", ["start", "submit", "answer", "solve", "hint", "reveal", "error"])
def test_storage_failure_does_not_break_gameplay(recording, client, create_room, moderator, monkeypatch, failure_point, caplog):
    recorder, store = recording
    real_insert = store.insert
    names_to_fail = {"start": "game_started", "submit": "question_submitted", "answer": "question_answered",
                     "solve": "game_solved", "hint": "hint_delivered", "reveal": "solution_revealed", "error": "game_error"}

    def fail(event):
        if event.event_name == names_to_fail[failure_point]:
            raise RuntimeError("PRIVATE_STORAGE_FAILURE")
        return real_insert(event)

    monkeypatch.setattr(store, "insert", fail)
    room = create_room()
    if failure_point == "error":
        assert client.get("/api/join/ZZZZ").status_code == 404
    else:
        moderator("Solved")
        assert post(client, room).json()["solved"] is True
        assert post(client, room, "hint").status_code == 200
        assert post(client, room, "reveal").status_code == 200
    assert recorder.dropped >= 1
    assert "PRIVATE_STORAGE_FAILURE" not in caplog.text


def test_invalid_clock_and_id_factory_are_fail_open(recording, client, create_room, monkeypatch):
    recorder, _ = recording
    monkeypatch.setattr(recorder, "_clock", lambda: datetime(2026, 11, 7))
    room = create_room()
    assert post(client, room).status_code == 200
    assert recorder.dropped == 1
    assert rows(recording) == []


def test_production_import_path_never_connects_or_activates(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    script = '''
import sqlite3

def forbidden(*args, **kwargs):
    raise AssertionError("default startup must not open a database")

sqlite3.connect = forbidden
import app
assert app.analytics_recorder.enabled is False
assert app.analytics_recorder.store is None
assert app.analytics_recorder._games == {}
'''
    env = {**os.environ, "USE_API": "false", "PYTHONDONTWRITEBYTECODE": "1",
           "ANALYTICS_ENABLED": "true", "ANALYTICS_DATABASE_PATH": str(tmp_path / "must-not-exist.sqlite3")}
    env.pop("OPENAI_API_KEY", None)
    subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1] / "backend",
                   env=env, check=True, capture_output=True, text=True)
    assert list(tmp_path.iterdir()) == []


def test_answer_and_hint_callbacks_are_idempotent(recording, client, create_room, isolated_app):
    room = create_room()
    internal = isolated_app.ROOMS[room["room_id"]]
    recorder, _ = recording
    attempt = recorder.question(internal, "offline")
    recorder.answered(internal, attempt, "unknown", "offline_stub")
    recorder.answered(internal, attempt, "unknown", "offline_stub")
    hint_attempt = recorder.hint_requested(internal, "offline")
    recorder.hint_delivered(internal, hint_attempt, 1)
    recorder.hint_delivered(internal, hint_attempt, 1)
    assert names(recording) == ["game_started", "question_submitted", "question_answered", "hint_requested", "hint_delivered"]
    assert recorder.dropped == 0


def test_ai_timeout_is_a_bounded_error_code(recording, client, create_room, moderator):
    from openai import APITimeoutError

    room = create_room()
    completion = moderator()
    completion.side_effect = APITimeoutError(request=Mock())
    response = post(client, room)
    assert response.status_code == 503
    assert response.json() == {"detail": "The moderator is unavailable. Please try again."}
    assert rows(recording)[-1].properties.error_code == "ai_timeout"


def test_optional_classifier_observer_failure_preserves_return(isolated_app):
    from game import classify_question

    def broken_observer(origin):
        raise RuntimeError("PRIVATE_OBSERVER_FAILURE")

    assert classify_question("Question?", "unused", None, observe_origin=broken_observer) == (
        "Unknown", "(offline mode)", [])


def test_id_generation_failure_is_fail_open(recording, client, create_room, monkeypatch):
    recorder, _ = recording
    monkeypatch.setattr(recorder, "_id", lambda: "invalid")
    room = create_room()
    assert post(client, room).status_code == 200
    assert recorder.dropped == 1
    assert rows(recording) == []


def test_no_new_public_routes_or_request_fields(recording, client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/api/create_room", "/api/join/{room_code}", "/api/mysteries", "/api/hint", "/api/reveal", "/api/message", "/api/feedback"}
    assert set(schema["components"]["schemas"]["MsgReq"]["properties"]) == {"room_id", "room_code", "text"}
    assert set(schema["components"]["schemas"]["MsgResp"]["properties"]) == {"reply", "solved"}
    assert rows(recording) == []
