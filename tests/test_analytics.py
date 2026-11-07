"""Pure schema tests; no emitters, persistence, HTTP, or real AI calls."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.analytics import MAX_COUNTER, MAX_EVENT_BYTES, validate_event


ID = "11111111-1111-4111-8111-111111111111"
TIME = "2026-11-07T12:30:00.000Z"
PROPERTIES = {
    "game_started": {},
    "question_submitted": {"attempt_id": ID},
    "question_answered": {"attempt_id": ID, "response_category": "yes", "response_origin": "ai_tool"},
    "hint_requested": {"attempt_id": ID, "pre_terminal": True},
    "hint_delivered": {"attempt_id": ID, "pre_terminal": True, "hint_number": 1},
    "game_solved": {"attempt_id": ID, "solve_method": "required_facts"},
    "solution_revealed": {"attempt_id": ID, "establishes_outcome": True},
    "game_abandoned": {"last_activity_at": "2026-11-07T12:00:00.000Z", "inactivity_seconds": 1800, "rule_version": "inactivity_v1"},
    "game_error": {"attempt_id": ID, "operation": "message", "error_code": "ai_failure", "stage": "processing"},
}
EVENTS = list(PROPERTIES)


def payload(name="game_started"):
    return {
        "schema_version": 1, "event_name": name, "event_id": ID,
        "environment": "test", "source": "derived" if name == "game_abandoned" else "server",
        "occurred_at": TIME, "recorded_at": TIME, "game_session_id": ID,
        "mystery_id": "ms-001", "browser_visit_id": None, "mode": "ai", "game_sequence": 1,
        "properties": deepcopy(PROPERTIES[name]),
    }


@pytest.mark.parametrize("name", EVENTS)
def test_all_events_round_trip_dict_json_bytes(name):
    data = payload(name)
    event = validate_event(data)
    assert event.event_name == name
    assert event.schema_version == 1
    assert event.event_id == UUID(ID)
    assert event.occurred_at == datetime(2026, 11, 7, 12, 30, tzinfo=timezone.utc)
    serialized = event.model_dump_json()
    assert json.loads(serialized)["occurred_at"] == TIME
    assert "browser_visit_id" in json.loads(serialized)  # Required nulls are retained.
    assert validate_event(serialized) == event
    assert validate_event(serialized.encode()) == event
    assert validate_event(event.model_dump()) == event
    assert data == payload(name)  # Validation does not mutate input.


@pytest.mark.parametrize("name", EVENTS)
@pytest.mark.parametrize("field", [
    "schema_version", "event_name", "event_id", "environment", "source",
    "occurred_at", "recorded_at", "game_session_id", "mystery_id",
    "browser_visit_id", "mode", "game_sequence", "properties",
])
def test_required_envelope_fields_cannot_be_omitted(name, field):
    data = payload(name)
    del data[field]
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("name,field", [
    (name, field) for name, props in PROPERTIES.items() for field in props
])
def test_required_event_properties_cannot_be_omitted(name, field):
    data = payload(name)
    del data["properties"][field]
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("name", EVENTS)
@pytest.mark.parametrize("location", ["envelope", "properties"])
def test_unknown_fields_forbidden_for_every_event(name, location):
    data = payload(name)
    target = data if location == "envelope" else data["properties"]
    target["unapproved_metadata"] = {"unexpected": "content"}
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("field", [
    "question", "raw_question", "response_text", "solution", "solution_summary",
    "private_facts", "fact_indices", "hint", "hint_text", "metadata",
    "exception", "traceback", "ip_address", "user_agent", "headers",
    "room_code", "api_key",
])
@pytest.mark.parametrize("location", ["envelope", "properties"])
def test_sensitive_content_fields_rejected(field, location):
    data = payload("game_error")
    target = data if location == "envelope" else data["properties"]
    target[field] = "SENSITIVE_SENTINEL"
    with pytest.raises(ValidationError) as error:
        validate_event(data)
    assert "SENSITIVE_SENTINEL" not in str(error.value)


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("schema_version", True), ("schema_version", 1.0), ("schema_version", "1"),
    ("event_name", "page_view"), ("event_name", None),
    ("environment", "prod"), ("source", "client"), ("source", "derived"),
    ("mode", "online"), ("mode", None),
    ("mystery_id", None), ("mystery_id", "../ms-001"), ("mystery_id", "ms-secret"),
    ("game_sequence", 0), ("game_sequence", -1), ("game_sequence", MAX_COUNTER + 1),
    ("game_sequence", True), ("game_sequence", 1.0), ("game_sequence", "1"),
    ("game_session_id", None), ("properties", []),
])
def test_invalid_envelope_values(field, value):
    data = payload()
    data[field] = value
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("field", ["event_id", "game_session_id", "browser_visit_id"])
@pytest.mark.parametrize("value", [
    "invalid", 123, b"11111111-1111-4111-8111-111111111111",
    "11111111111141118111111111111111", "11111111-1111-1111-8111-111111111111",
    "00000000-0000-0000-0000-000000000000",
])
def test_invalid_uuid_and_non_v4_ids(field, value):
    data = payload()
    data[field] = value
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("field", ["occurred_at", "recorded_at"])
@pytest.mark.parametrize("value", [
    "2026-11-07T12:30:00", "2026-11-07T12:30:00.000+01:00",
    "2026-11-07T12:30:00.000-00:00", "2026-11-07T12:30:00Z",
    "2026-11-07T12:30:00.000001Z", "2026-02-30T12:30:00.000Z",
    "yesterday", 1794054600, datetime(2026, 11, 7),
])
def test_invalid_timestamp_format_timezone_precision(field, value):
    data = payload()
    data[field] = value
    with pytest.raises(ValidationError):
        validate_event(data)


def test_recording_time_may_be_later_but_not_earlier():
    data = payload()
    data["recorded_at"] = "2026-11-07T12:31:00.000Z"
    validate_event(data)
    data["recorded_at"] = "2026-11-07T12:29:59.999Z"
    with pytest.raises(ValidationError):
        validate_event(data)


def test_python_uuid_utc_objects_and_zero_offset_strings():
    data = payload()
    data.update(event_id=UUID(ID), browser_visit_id=UUID(ID),
                occurred_at=datetime(2026, 11, 7, 12, 30, tzinfo=timezone.utc),
                recorded_at="2026-11-07T12:30:00.000+00:00")
    assert validate_event(data).model_dump(mode="json")["recorded_at"] == TIME


@pytest.mark.parametrize("name", [n for n in EVENTS if n != "game_error"])
@pytest.mark.parametrize("field", ["game_session_id", "mystery_id", "mode", "game_sequence"])
def test_game_events_require_non_null_associations(name, field):
    data = payload(name)
    data[field] = None
    with pytest.raises(ValidationError):
        validate_event(data)


def test_unassociated_error_requires_explicit_nullable_fields():
    data = payload("game_error")
    data.update(game_session_id=None, mystery_id=None, game_sequence=None, mode=None)
    data["properties"]["stage"] = "before_acceptance"
    assert validate_event(data).game_session_id is None
    # A creation error can know a catalog mystery without having created a game.
    data["mystery_id"] = "ms-001"
    validate_event(data)
    data["properties"]["stage"] = "processing"
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("changes", [
    {"game_sequence": None}, {"game_session_id": None}, {"mystery_id": None},
])
def test_error_association_consistency(changes):
    data = payload("game_error")
    data.update(changes)
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("name,field,value", [
    ("game_started", "start_source", "advertisement"),
    ("question_submitted", "attempt_id", "invalid"),
    ("question_answered", "response_category", "raw response"),
    ("question_answered", "response_origin", "provider text"),
    ("hint_requested", "pre_terminal", 1),
    ("hint_delivered", "pre_terminal", "true"),
    ("hint_delivered", "hint_number", 0),
    ("hint_delivered", "hint_number", MAX_COUNTER + 1),
    ("hint_delivered", "hint_number", True),
    ("game_solved", "solve_method", "revealed"),
    ("solution_revealed", "establishes_outcome", "false"),
    ("game_abandoned", "inactivity_seconds", 1799),
    ("game_abandoned", "inactivity_seconds", 1800.0),
    ("game_abandoned", "rule_version", "other"),
    ("game_abandoned", "last_activity_at", "2026-11-07T12:00:00Z"),
    ("game_error", "operation", "arbitrary_url"),
    ("game_error", "error_code", "exception message"),
    ("game_error", "stage", "unknown"),
    ("game_error", "http_status", 399), ("game_error", "http_status", 600),
    ("game_error", "http_status", True),
])
def test_invalid_event_specific_values(name, field, value):
    data = payload(name)
    data["properties"][field] = value
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("name", ["question_answered", "hint_delivered", "game_error"])
@pytest.mark.parametrize("value", [-1, 300001, 1.5, "1", True, float("nan"), float("inf")])
def test_latency_rejects_out_of_bounds_coercion_and_nonfinite(name, value):
    data = payload(name)
    data["properties"]["latency_ms"] = value
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("name", ["question_answered", "hint_delivered", "game_error"])
@pytest.mark.parametrize("value", [0, 300000])
def test_latency_boundaries(name, value):
    data = payload(name)
    data["properties"]["latency_ms"] = value
    assert validate_event(data).properties.latency_ms == value


@pytest.mark.parametrize("value", [1, MAX_COUNTER])
def test_positive_integer_boundaries(value):
    data = payload("hint_delivered")
    data["game_sequence"] = value
    data["properties"]["hint_number"] = value
    assert validate_event(data).game_sequence == value


@pytest.mark.parametrize("value", [400, 599])
def test_http_status_boundaries(value):
    data = payload("game_error")
    data["properties"]["http_status"] = value
    assert validate_event(data).properties.http_status == value


@pytest.mark.parametrize("field", ["content_revision", "app_revision"])
@pytest.mark.parametrize("value", ["", "a" * 65, "raw question text", "127.0.0.1", "user@example.com", {"secret": "value"}])
def test_revision_fields_do_not_accept_arbitrary_metadata(field, value):
    data = payload()
    data[field] = value
    with pytest.raises(ValidationError):
        validate_event(data)


@pytest.mark.parametrize("revision", ["a" * 7, "a" * 40, "1.2.3", "v1.2.3-rc.1", "1.2.3-" + "x" * 58])
def test_revision_formats_and_maximum_length(revision):
    data = payload()
    data["app_revision"] = revision
    assert validate_event(data).app_revision == revision


@pytest.mark.parametrize("mode,origin,category", [
    ("offline", "offline_stub", "unknown"), ("ai", "ai_tool", "yes"), ("ai", "ai_fallback", "unknown"),
])
def test_consistent_response_mode(mode, origin, category):
    data = payload("question_answered")
    data["mode"] = mode
    data["properties"].update(response_origin=origin, response_category=category)
    validate_event(data)


@pytest.mark.parametrize("mode,origin,category", [
    ("offline", "ai_tool", "unknown"), ("offline", "offline_stub", "yes"),
    ("ai", "offline_stub", "unknown"), ("ai", "ai_fallback", "solved"),
])
def test_inconsistent_response_mode(mode, origin, category):
    data = payload("question_answered")
    data["mode"] = mode
    data["properties"].update(response_origin=origin, response_category=category)
    with pytest.raises(ValidationError):
        validate_event(data)


def test_abandonment_requires_derived_source_and_exact_interval():
    data = payload("game_abandoned")
    data["source"] = "server"
    with pytest.raises(ValidationError):
        validate_event(data)
    data["source"] = "derived"
    data["properties"]["last_activity_at"] = "2026-11-07T12:00:00.001Z"
    with pytest.raises(ValidationError):
        validate_event(data)


def test_payload_size_guard_and_malformed_json():
    valid = validate_event(payload()).model_dump_json()
    # JSON whitespace counts toward the transport bound, even though it is not persisted.
    padded = valid + " " * (MAX_EVENT_BYTES - len(valid.encode()))
    assert validate_event(padded).event_name == "game_started"
    for data in [padded + " ", b" " * (MAX_EVENT_BYTES + 1), "{", "null", "[]"]:
        with pytest.raises(ValueError):
            validate_event(data)


def test_validated_models_are_frozen():
    event = validate_event(payload("hint_delivered"))
    with pytest.raises(ValidationError):
        event.mode = "offline"
    with pytest.raises(ValidationError):
        event.properties.hint_number = 0


@pytest.mark.parametrize("mid", ["ms-000", "ms-99999999"])
def test_mystery_id_format_boundaries_without_catalog_lookup(mid):
    data = payload()
    data["mystery_id"] = mid
    assert validate_event(data).mystery_id == mid


@pytest.mark.parametrize("mid", ["ms-01", "ms-123456789"])
def test_mystery_id_outside_format_bounds(mid):
    data = payload()
    data["mystery_id"] = mid
    with pytest.raises(ValidationError):
        validate_event(data)


def test_optional_nulls_and_false_booleans_are_preserved():
    data = payload("solution_revealed")
    data["properties"]["establishes_outcome"] = False
    data.update(app_revision=None, content_revision=None, browser_visit_id=ID)
    event = validate_event(data)
    assert validate_event(event.model_dump_json()) == event
    assert event.properties.establishes_outcome is False


def test_python_submillisecond_datetime_rejected():
    data = payload()
    data["occurred_at"] = datetime(2026, 11, 7, 12, 30, microsecond=1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        validate_event(data)


def test_models_are_revalidated_even_after_trusted_copy_bypass():
    event = validate_event(payload("hint_delivered"))
    invalid = event.model_copy(update={"properties": event.properties.model_copy(update={"hint_number": 0})})
    with pytest.raises(ValidationError):
        validate_event(invalid)


def test_validation_has_no_catalog_or_filesystem_dependency(monkeypatch):
    from pathlib import Path

    def forbidden(*args, **kwargs):
        raise AssertionError("schema validation must not access files")

    monkeypatch.setattr(Path, "open", forbidden)
    assert validate_event(payload()).mystery_id == "ms-001"
