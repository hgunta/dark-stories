"""Durable feedback adapter tests: no secrets, OpenAI calls or external database."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.feedback_storage import SQLiteFeedbackStore
from backend.feedback_report import main as report_main
from backend.feedback_local import main as local_main


@pytest.fixture
def store(tmp_path):
    result = SQLiteFeedbackStore(tmp_path / "feedback.sqlite3")
    result.initialize()
    return result


def test_init_explicit_path_and_persistence_across_reopen(store):
    assert store.submit("room-1", "ms-001", 5, "none") == "created"
    assert store.count() == 1
    reopened = SQLiteFeedbackStore(store.path)
    assert reopened.count() == 1
    assert reopened.submit("room-1", "ms-001", 5, "none") == "duplicate"
    assert reopened.submit("room-2", "ms-001", 1, "spoiler") == "created"
    data = reopened.summarize()
    assert data["total"] == 2 and data["average_rating"] == 3
    assert data["ratings"] == {"1": 1, "5": 1}
    assert data["issues"] == {"none": 1, "spoiler": 1}
    assert data["mysteries"] == [{"mystery_id": "ms-001", "count": 2, "average_rating": 3}]


def test_missing_db_not_created_by_reporting(tmp_path):
    path = tmp_path / "missing.sqlite3"
    store = SQLiteFeedbackStore(path)
    with pytest.raises(sqlite3.OperationalError):
        store.summarize()
    assert not path.exists()


@pytest.mark.parametrize("path", [None, "", " ", ":memory:", "file:feedback.sqlite3", 42])
def test_explicit_path_required(path):
    with pytest.raises(ValueError):
        SQLiteFeedbackStore(path)


def test_no_directory_creation(tmp_path):
    path = tmp_path / "missing" / "feedback.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteFeedbackStore(path).initialize()
    assert not path.parent.exists()


@pytest.mark.parametrize("rating,issue", [
    (0, "none"), (6, "none"), (True, "none"), ("5", "none"),
    (4.5, "none"), (5, "malicious"), (None, "none"),
])
def test_invalid_feedback_rejected_without_writes(store, rating, issue):
    with pytest.raises((ValueError, TypeError)):
        store.submit("room-1", "ms-001", rating, issue)
    assert store.count() == 0


def test_mystery_and_room_validation(store):
    for bad in ("../../secrets", "private", "ms-001\n", ""):
        with pytest.raises(ValueError):
            store.submit("room-1", bad, 5, "none")
    with pytest.raises(ValueError):
        store.submit("", "ms-001", 5, "none")
    assert store.count() == 0


def test_no_raw_room_ids_or_text_persisted(store):
    store.submit("SENSITIVE_ROOM_SENTINEL", "ms-002", 2, "incorrect_answer")
    with sqlite3.connect(store.path) as db:
        cols = {r[1] for r in db.execute("PRAGMA table_info(feedback)")}
        assert "room_id" not in cols and "raw_text" not in cols
        row = db.execute("SELECT * FROM feedback").fetchone()
        assert not any("SENSITIVE_ROOM_SENTINEL" in str(value) for value in row)
    report = json.dumps(store.summarize())
    assert "SENSITIVE_ROOM_SENTINEL" not in report
    assert "room_digest" not in report


def test_aggregate_counts_by_mystery(store):
    store.submit("one", "ms-001", 5, "none")
    store.submit("two", "ms-001", 3, "spoiler")
    store.submit("three", "ms-002", 4, "other")
    report = store.summarize()
    assert report["total"] == 3 and report["average_rating"] == 4
    assert [m["count"] for m in report["mysteries"]] == [2, 1]


def test_retries_and_concurrent_writes_are_idempotent(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: SQLiteFeedbackStore(store.path).submit(
            "competing", "ms-001", 5, "none"), range(4)))
    assert results.count("created") == 1
    assert results.count("duplicate") == 3
    assert store.count() == 1


def test_report_cli_contains_aggregates_only(store, capsys):
    store.submit("PRIVATE_ROOM", "ms-003", 2, "spoiler")
    report_main(["--database", str(store.path)])
    printed = capsys.readouterr().out
    report = json.loads(printed)
    assert report["total"] == 1
    assert "PRIVATE_ROOM" not in printed
    assert "room_digest" not in printed


def test_explicit_retention_cleanup(store):
    store.submit("old", "ms-001", 5, "none")
    store.submit("new", "ms-002", 4, "none")
    now = datetime(2026, 11, 7, 20, tzinfo=timezone.utc)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE feedback SET created_at = ? WHERE mystery_id = 'ms-001'",
                   ((now-timedelta(days=40)).isoformat(timespec="milliseconds"),))
        db.execute("UPDATE feedback SET created_at = ? WHERE mystery_id = 'ms-002'",
                   (now.isoformat(timespec="milliseconds"),))
    assert store.delete_expired(now=now) == 1
    assert store.count() == 1
    assert store.delete_expired(now=now) == 0


def test_duplicate_room_persists_across_restarts_even_if_rating_changes(store):
    assert store.submit("same", "ms-001", 5, "none") == "created"
    newer = SQLiteFeedbackStore(store.path)
    assert newer.submit("same", "ms-002", 1, "spoiler") == "duplicate"
    assert newer.summarize()["mysteries"][0]["mystery_id"] == "ms-001"


def test_local_launcher_binds_loopback_only(store, monkeypatch, isolated_app):
    from unittest.mock import Mock
    # The launcher intentionally swaps the module-level store. Restore that
    # global after this test so other test cases see normal startup defaults.
    monkeypatch.setattr(isolated_app, "feedback_store", isolated_app.feedback_store)
    run = Mock()
    monkeypatch.setattr("uvicorn.run", run)
    local_main(["--database", str(store.path), "--port", "8766"])
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["proxy_headers"] is False
    with pytest.raises(SystemExit):
        local_main(["--database", str(store.path), "--port", "0"])


def test_api_can_use_explicit_sqlite_store(client, create_room, isolated_app, store, monkeypatch):
    monkeypatch.setattr(isolated_app, "feedback_store", store)
    room = create_room()
    assert client.post("/api/feedback", json={"room_id": room["room_id"], "rating": 5}).status_code == 409
    assert client.post("/api/reveal", json={"room_id": room["room_id"], "text": "/reveal"}).status_code == 200
    request = {"room_id": room["room_id"], "rating": 5, "issue": "none"}
    assert client.post("/api/feedback", json=request).status_code == 201
    assert client.post("/api/feedback", json=request).status_code == 409
    assert SQLiteFeedbackStore(store.path).count() == 1
    assert isolated_app.analytics_recorder.enabled is False
    assert client.get("/api/feedback/list").status_code == 404


def test_database_failure_is_generic_and_gameplay_still_works(client, create_room, isolated_app, tmp_path, monkeypatch):
    store = SQLiteFeedbackStore(tmp_path / "uninitialized.sqlite3")
    monkeypatch.setattr(isolated_app, "feedback_store", store)
    room = create_room()
    client.post("/api/reveal", json={"room_id": room["room_id"], "text": "/reveal"})
    response = client.post("/api/feedback", json={"room_id": room["room_id"], "rating": 4})
    assert response.status_code == 503
    assert response.json() == {"detail": "Feedback temporarily unavailable"}
    assert client.get("/api/mysteries").status_code == 200


def test_normal_production_startup_still_defaults_to_memory(isolated_app):
    from backend.feedback import FeedbackStore
    assert isinstance(isolated_app.feedback_store, FeedbackStore)
