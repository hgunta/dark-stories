"""Local SQLite guarantees only; all files are explicitly allocated under tmp_path."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
from threading import Barrier
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.analytics import validate_event
from backend.analytics_storage import EventConflictError, SQLiteEventStore


def uid(number):
    return str(UUID(int=number, version=4))


def event(name="game_started", number=1, sequence=1, game=100, **changes):
    props = {
        "game_started": {}, "question_submitted": {"attempt_id": uid(number)},
        "question_answered": {"attempt_id": uid(number), "response_category": "yes", "response_origin": "ai_tool"},
        "hint_requested": {"attempt_id": uid(number), "pre_terminal": True},
        "hint_delivered": {"attempt_id": uid(number), "pre_terminal": True, "hint_number": 1},
        "game_solved": {"attempt_id": uid(number), "solve_method": "required_facts"},
        "solution_revealed": {"attempt_id": uid(number), "establishes_outcome": True},
        "game_abandoned": {"last_activity_at": "2026-11-07T12:00:00.000Z", "inactivity_seconds": 1800, "rule_version": "inactivity_v1"},
        "game_error": {"attempt_id": uid(number), "operation": "message", "error_code": "ai_failure", "stage": "processing"},
    }
    data = dict(schema_version=1, event_name=name, event_id=uid(number), environment="test",
                source="derived" if name == "game_abandoned" else "server",
                occurred_at="2026-11-07T12:30:00.000Z", recorded_at="2026-11-07T12:30:00.000Z",
                game_session_id=uid(game), mystery_id="ms-001", browser_visit_id=None,
                mode="ai", game_sequence=sequence, properties=props[name])
    data.update(changes)
    return validate_event(data)


@pytest.fixture
def store(tmp_path):
    result = SQLiteEventStore(tmp_path / "analytics.sqlite3")
    result.initialize()
    return result


@pytest.mark.parametrize("name", [
    "game_started", "question_submitted", "question_answered", "hint_requested",
    "hint_delivered", "game_solved", "solution_revealed", "game_abandoned", "game_error",
])
def test_all_nine_types_round_trip(store, name):
    original = event(name)
    assert store.insert(original) is True
    assert store.get(original.event_id, environment="test") == original
    assert store.read(environment="test") == [original]


def test_explicit_initialization_is_idempotent_and_preserves_rows(tmp_path):
    path = tmp_path / "literal ? # database.sqlite3"
    store = SQLiteEventStore(path)
    assert not path.exists()
    with pytest.raises(sqlite3.OperationalError):
        store.read(environment="test")
    assert not path.exists()
    store.initialize()
    store.insert(event())
    store.initialize()
    assert len(store.read(environment="test")) == 1
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        names = {row[1] for row in db.execute("PRAGMA index_list(analytics_events)")}
        assert {"analytics_game", "analytics_terminal", "analytics_name_time", "analytics_time", "analytics_recorded"} <= names


@pytest.mark.parametrize("path", [None, "", " ", ":memory:", "file:database.sqlite3", 123])
def test_no_default_or_implicit_sqlite_location(path):
    with pytest.raises(ValueError):
        SQLiteEventStore(path)


def test_missing_parent_not_created(tmp_path):
    path = tmp_path / "missing" / "analytics.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteEventStore(path).initialize()
    assert not path.parent.exists()


def test_reopen_local_file_and_retry(tmp_path):
    path = tmp_path / "analytics.sqlite3"
    first = SQLiteEventStore(path)
    first.initialize()
    original = event()
    first.insert(original)
    reopened = SQLiteEventStore(path)
    reopened.initialize()
    assert reopened.get(original.event_id, environment="test") == original
    assert reopened.insert(original) is False
    assert len(reopened.read(environment="test")) == 1


def test_exact_canonical_retries_are_noops(store):
    original = event()
    assert store.insert(original)
    assert store.insert(validate_event(original.model_dump_json())) is False
    data = original.model_dump(mode="json")
    data.pop("app_revision")  # Omitted optional defaults canonicalize to null.
    data.pop("content_revision")
    assert store.insert(validate_event(data)) is False
    assert store.read(environment="test") == [original]


@pytest.mark.parametrize("change", [
    {"mystery_id": "ms-002"}, {"environment": "staging"},
    {"recorded_at": "2026-11-07T12:31:00.000Z"},
])
def test_same_event_id_with_changed_content_conflicts(store, change):
    original = event()
    store.insert(original)
    data = original.model_dump(mode="json")
    data.update(change)
    with pytest.raises(EventConflictError):
        store.insert(validate_event(data))
    assert store.read(environment="test") == [original]


@pytest.mark.parametrize("name", ["game_started", "question_submitted", "game_abandoned", "game_error"])
def test_changed_event_id_cannot_duplicate_semantic_key(store, name):
    first = event(name)
    store.insert(first)
    data = first.model_dump(mode="json")
    data.update(event_id=uid(2), game_sequence=2)
    with pytest.raises(EventConflictError):
        store.insert(validate_event(data))
    assert store.read(environment="test") == [first]


def test_same_game_sequence_conflicts_but_environment_is_partitioned(store):
    store.insert(event())
    with pytest.raises(EventConflictError):
        store.insert(event("hint_requested", number=2))
    assert store.insert(event("hint_requested", number=3, environment="staging"))
    assert len(store.read(environment="test")) == len(store.read(environment="staging")) == 1


@pytest.mark.parametrize("first,second", [
    ("game_solved", "solution_revealed"), ("solution_revealed", "game_solved"),
    ("game_solved", "game_solved"), ("solution_revealed", "solution_revealed"),
])
def test_only_one_terminal_outcome_even_with_distinct_attempts(store, first, second):
    original = event(first)
    store.insert(original)
    assert store.insert(original) is False
    with pytest.raises(EventConflictError):
        store.insert(event(second, number=2, sequence=2))
    assert store.read(environment="test") == [original]


def test_repeat_reveal_records_interaction_without_second_outcome(store):
    store.insert(event("game_solved", sequence=2))
    later = event("solution_revealed", number=2, sequence=3,
                  properties={"attempt_id": uid(2), "establishes_outcome": False})
    assert store.insert(later)
    assert store.insert(later) is False
    assert len(store.read(environment="test")) == 2
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute("SELECT SUM(terminal) FROM analytics_events").fetchone()[0] == 1


@pytest.mark.parametrize("terminal_sequence", [None, 3])
def test_nonterminal_reveal_requires_earlier_known_terminal(store, terminal_sequence):
    if terminal_sequence:
        store.insert(event("game_solved", sequence=terminal_sequence))
    later = event("solution_revealed", number=2, sequence=2,
                  properties={"attempt_id": uid(2), "establishes_outcome": False})
    with pytest.raises(EventConflictError):
        store.insert(later)


def test_late_earlier_terminal_is_rejected_not_silently_reclassified(store):
    original = event("solution_revealed", sequence=10)
    store.insert(original)
    with pytest.raises(EventConflictError):
        store.insert(event("game_solved", number=2, sequence=5))
    assert store.read(environment="test") == [original]


def test_transaction_rolls_back_trigger_side_effects_and_remains_usable(store):
    with closing(sqlite3.connect(store.path)) as db:
        db.executescript("""CREATE TABLE rollback_probe (value INTEGER);
            CREATE TRIGGER fail_insert AFTER INSERT ON analytics_events BEGIN
              INSERT INTO rollback_probe VALUES (1);
              SELECT RAISE(FAIL, 'simulated failure after insert');
            END;""")
    with pytest.raises(EventConflictError):
        store.insert(event())
    assert store.read(environment="test") == []
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM rollback_probe").fetchone()[0] == 0
        db.execute("DROP TRIGGER fail_insert")
    assert store.insert(event())


def test_future_database_version_rejected_without_schema_changes(tmp_path):
    path = tmp_path / "future.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA user_version = 99")
    with pytest.raises(ValueError):
        SQLiteEventStore(path).initialize()
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


@pytest.mark.parametrize("competing", ["identical", "conflicting_id", "terminal"])
def test_competing_writers_are_serialized(store, competing):
    first = event("game_solved")
    second = first if competing == "identical" else (
        event("game_solved", mystery_id="ms-002") if competing == "conflicting_id"
        else event("solution_revealed", number=2, sequence=2))
    barrier = Barrier(2)

    def write(item):
        independent = SQLiteEventStore(store.path)
        barrier.wait(timeout=5)
        try:
            return independent.insert(item)
        except EventConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [first, second]))
    assert results.count(True) == 1
    assert results.count(False if competing == "identical" else "conflict") == 1
    assert len(store.read(environment="test")) == 1


@pytest.mark.parametrize("raw", [{}, '{"question":"private"}', b"invalid", None, 42])
def test_only_validated_models_are_accepted(store, raw):
    with pytest.raises(TypeError):
        store.insert(raw)
    assert store.read(environment="test") == []


@pytest.mark.parametrize("field", ["raw_question", "solution", "private_facts", "hint_text", "ip_address", "user_agent", "exception", "metadata"])
def test_bypassed_sensitive_properties_rejected_before_write(store, field):
    original = event("question_submitted")
    corrupted = original.model_copy(update={"properties": {"attempt_id": uid(1), field: "PRIVATE_SENTINEL"}})
    with pytest.raises(ValidationError):
        store.insert(corrupted)
    assert store.read(environment="test") == []


def test_malformed_model_rejected_before_database_access(tmp_path):
    store = SQLiteEventStore(tmp_path / "not-created.sqlite3")
    malformed = event().model_copy(update={"event_id": "invalid"})
    with pytest.raises(ValidationError):
        store.insert(malformed)
    assert not store.path.exists()


def test_sequence_and_timestamp_ordering_bounded_reads(store):
    events = [event("question_submitted", number=i, sequence=i) for i in [3, 1, 2]]
    for item in events:
        store.insert(item)
    assert [e.game_sequence for e in store.read(environment="test", game_session_id=uid(100))] == [1, 2, 3]
    assert [e.game_sequence for e in store.read(environment="test", limit=1, offset=1)] == [2]
    assert len(store.read(environment="test", event_name="question_submitted")) == 3
    assert store.read(environment="test", event_name="hint_delivered") == []
    assert len(store.read(environment="test", since="2026-11-07T12:30:00.000Z")) == 3
    assert store.read(environment="test", until="2026-11-07T12:30:00.000Z") == []
    assert store.get(uid(999), environment="test") is None
    assert store.get(uid(1), environment="staging") is None


@pytest.mark.parametrize("arguments", [
    {"limit": 0}, {"limit": 1001}, {"limit": True}, {"limit": "10"},
    {"offset": -1}, {"offset": 100001}, {"offset": False},
    {"event_name": "game_started' OR 1=1 --"}, {"game_session_id": "' OR 1=1 --"},
    {"environment": "test' OR 1=1 --"}, {"since": "yesterday"},
    {"since": "2026-11-07T12:30:00.000Z", "until": "2026-11-07T12:00:00.000Z"},
])
def test_query_filters_are_validated_not_interpolated(store, arguments):
    with pytest.raises(ValueError):
        store.read(**{"environment": "test", **arguments})


def test_unassociated_errors_can_coexist_and_are_semantically_deduplicated(store):
    for number in [1, 2]:
        store.insert(event("game_error", number=number, game_session_id=None,
                           game_sequence=None, mystery_id=None, mode=None,
                           properties={"attempt_id": uid(number), "operation": "join",
                                       "error_code": "unknown_room", "stage": "before_acceptance"}))
    assert len(store.read(environment="test")) == 2


def test_stored_events_are_validated_again_on_read(store):
    store.insert(event())
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("UPDATE analytics_events SET payload = ?", ('{"raw_question":"private"}',))
        db.commit()
    with pytest.raises(ValidationError):
        store.read(environment="test")


def test_same_sequence_is_allowed_for_different_games(store):
    store.insert(event())
    assert store.insert(event(number=2, game=200))
    assert len(store.read(environment="test")) == 2


def test_occurrence_time_orders_globally_and_filter_bounds_are_normalized(store):
    later = event("question_submitted", number=1, sequence=1,
                  occurred_at="2026-11-07T12:31:00.000Z", recorded_at="2026-11-07T12:31:00.000Z")
    earlier = event("question_submitted", number=2, sequence=2)
    store.insert(later)
    store.insert(earlier)
    assert store.read(environment="test") == [earlier, later]
    assert store.read(environment="test", game_session_id=uid(100)) == [later, earlier]
    assert store.read(environment="test", since=datetime(2026, 11, 7, 12, 31, tzinfo=timezone.utc)) == [later]


def test_query_pagination_boundaries(store):
    store.insert(event())
    assert len(store.read(environment="test", limit=1000, offset=0)) == 1
    assert store.read(environment="test", limit=1, offset=100000) == []


def test_unassociated_error_semantic_key_cannot_change_game_association(store):
    first = event("game_error", game_session_id=None, game_sequence=None, mystery_id=None)
    store.insert(first)
    conflicting = event("game_error", number=2, properties=first.properties.model_dump())
    with pytest.raises(EventConflictError):
        store.insert(conflicting)
    assert store.read(environment="test") == [first]
