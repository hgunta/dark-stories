"""Deterministic aggregate fixtures; no real players, collection, or OpenAI."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.analytics import validate_event
from backend.analytics_reporting import build_report
from backend.analytics_sample import generate_sample
from backend.analytics_storage import SQLiteEventStore
from test_analytics_storage import event, uid

NOW = datetime(2026, 11, 7, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    count = generate_sample(path, now=NOW)
    store = SQLiteEventStore(path)
    return path, store, count


def report(events, **kwargs):
    return build_report(events, as_of=NOW, **kwargs)


def test_empty_dataset_has_no_fabricated_rates():
    result = report([])
    assert result["summary"]["game_starts"] == 0
    for metric in ["solve_rate", "reveal_rate", "average_question_attempts", "average_hints_delivered"]:
        assert result["summary"][metric] is None
    assert result["abandonment_rate"] is None and result["replay_rate"] is None
    assert result["mysteries"] == []


def test_synthetic_metrics_known_denominators_and_coverage(sample):
    _, store, count = sample
    result = report(store.snapshot(environment="test"))
    s = result["summary"]
    assert result["dataset_label"] == "Synthetic sample data"
    assert result["events_loaded"] == count
    assert s["game_starts"] == 5
    assert s["question_attempts"] == 4
    assert s["question_responses"] == 3
    assert s["average_question_attempts"] == .8
    assert s["hints_delivered"] == 2
    assert s["average_hints_delivered"] == .4
    assert s["mature_games"] == 4 and s["immature_games"] == 1
    assert s["solved_games"] == s["revealed_games"] == 1
    assert s["solve_rate"] == s["reveal_rate"] == .25
    assert s["unresolved_games"] == 3
    assert s["unclassified_games"] == 0
    assert result["coverage"]["unknown_question_completions"] == 1
    assert result["coverage"]["games_without_browser_visit"] == 5
    mysteries = {m["mystery_id"]: m for m in result["mysteries"]}
    assert mysteries["ms-001"]["game_starts"] == 2
    assert mysteries["ms-001"]["solve_rate"] == .5
    assert mysteries["ms-002"]["reveal_rate"] == .5
    assert mysteries["ms-003"]["solve_rate"] is None
    assert all(m["low_sample"] for m in mysteries.values())


def test_offline_data_is_a_separate_cohort(sample):
    _, store, _ = sample
    result = report(store.snapshot(environment="test"), mode="offline")
    assert result["summary"]["game_starts"] == 1
    assert result["summary"]["reveal_rate"] == 1
    assert result["summary"]["solve_rate"] == 0
    assert result["summary"]["question_attempts"] == 1


def test_duplicate_input_and_storage_retries_do_not_inflate_metrics(sample):
    _, store, _ = sample
    events = store.snapshot(environment="test")
    for item in events:
        assert store.insert(item) is False
    canonical = report(events)
    duplicated = report(events + events)
    assert duplicated["summary"] == canonical["summary"]
    assert duplicated["coverage"]["duplicate_rows_ignored"] == len(events)
    changed_id = events[0].model_copy(update={"event_id": uid(99999)})
    assert report(events + [changed_id])["summary"] == canonical["summary"]


def test_conflicting_ids_do_not_choose_a_favorable_outcome():
    start = event()
    conflict = start.model_copy(update={"mystery_id": "ms-002"})
    result = report([start, conflict])
    assert result["summary"]["game_starts"] == 0
    assert result["coverage"]["conflicting_event_ids"] == 1


def test_orphans_and_sequence_gaps_are_visible_not_silent_success():
    start = event()
    unanswered = event("question_submitted", number=2, sequence=3)
    orphan = event("question_answered", number=3, game=200, sequence=2)
    result = report([start, unanswered, orphan])
    assert result["summary"]["game_starts"] == 1
    assert result["summary"]["question_attempts"] == 1
    assert result["summary"]["unclassified_games"] == 1
    assert result["coverage"]["events_without_unique_start"] == 1
    assert result["coverage"]["games_with_sequence_gaps_or_collisions"] == 1
    assert result["coverage"]["unanswered_question_attempts"] == 1


def test_unknown_completion_distinct_from_observed_failure():
    start = event()
    attempt = event("question_submitted", number=2, sequence=2)
    failure = event("game_error", number=3, sequence=3, properties={
        "attempt_id": uid(2), "operation": "message", "error_code": "ai_failure", "stage": "processing"})
    result = report([start, attempt, failure])
    assert result["coverage"]["unanswered_question_attempts"] == 1
    assert result["coverage"]["unknown_question_completions"] == 0


def test_solved_answer_without_solve_event_not_inferred_as_solve():
    start = event()
    attempt = event("question_submitted", number=2, sequence=2)
    answer = event("question_answered", number=3, sequence=3, properties={
        "attempt_id": uid(2), "response_category": "solved", "response_origin": "ai_tool"})
    result = report([start, attempt, answer])
    assert result["summary"]["solved_games"] == 0
    assert result["summary"]["unclassified_games"] == 1
    assert result["coverage"]["games_with_terminal_issues"] == 1


def test_conflicting_terminal_assertions_and_false_reveals_are_not_counted_twice():
    start = event()
    reveal = event("solution_revealed", number=2, sequence=2)
    false_reveal = event("solution_revealed", number=3, sequence=3, properties={"attempt_id": uid(3), "establishes_outcome": False})
    assert report([start, reveal, false_reveal])["summary"]["revealed_games"] == 1
    solved = event("game_solved", number=4, sequence=4)
    result = report([start, reveal, false_reveal, solved])
    assert result["summary"]["solved_games"] == result["summary"]["revealed_games"] == 0
    assert result["summary"]["unclassified_games"] == 1


def test_hints_require_a_matching_preterminal_request():
    start = event()
    orphan_hint = event("hint_delivered", number=2, sequence=2)
    result = report([start, orphan_hint])
    assert result["summary"]["hints_delivered"] == 0
    assert result["coverage"]["orphan_or_misordered_hint_deliveries"] == 1
    request = event("hint_requested", number=2, sequence=2, properties={"attempt_id": uid(2), "pre_terminal": False})
    delivered = event("hint_delivered", number=3, sequence=3, properties={"attempt_id": uid(2), "pre_terminal": False, "hint_number": 1})
    assert report([start, request, delivered])["summary"]["hints_delivered"] == 0


def test_maturity_boundary_and_as_of_exclusion():
    start = event()
    reveal = event("solution_revealed", number=2, sequence=2)
    result = build_report([start, reveal], as_of=datetime(2026, 11, 7, 13, 0, tzinfo=timezone.utc))
    assert result["summary"]["mature_games"] == 1
    assert result["summary"]["reveal_rate"] == 1
    result = build_report([start, reveal], as_of=datetime(2026, 11, 7, 12, 59, 59, 999000, tzinfo=timezone.utc))
    assert result["summary"]["mature_games"] == 0
    assert result["summary"]["reveal_rate"] is None
    result = build_report([start, reveal], as_of=datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc))
    assert result["summary"]["game_starts"] == 0
    assert result["coverage"]["future_events_excluded"] == 2


def test_mixed_mode_games_flagged_and_no_mode_blending():
    start = event()
    offline = event("question_submitted", number=2, sequence=2, mode="offline")
    result = report([start, offline])
    assert result["summary"]["question_attempts"] == 0
    assert result["summary"]["unclassified_games"] == 1
    assert result["coverage"]["mixed_mode_games"] == 1


def test_abandonment_and_replay_remain_unavailable_even_with_an_event():
    result = report([event(), event("game_abandoned", number=2, sequence=2)])
    assert result["abandonment_rate"] is None and result["replay_rate"] is None
    assert result["coverage"]["abandonment_events_not_interpreted"] == 1


def test_snapshot_is_read_only_bounded_and_does_not_create_missing_db(sample, tmp_path):
    path, store, count = sample
    before = path.read_bytes()
    assert len(store.snapshot(environment="test")) == count
    assert path.read_bytes() == before
    with pytest.raises(ValueError):
        store.snapshot(environment="test", limit=1)
    with pytest.raises(Exception):
        SQLiteEventStore(tmp_path / "missing.sqlite3").snapshot(environment="test")
    assert not (tmp_path / "missing.sqlite3").exists()


def test_sample_refuses_existing_database_and_labels_every_row(sample):
    path, store, _ = sample
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        generate_sample(path, now=NOW)
    assert path.read_bytes() == before
    assert all(e.app_revision == "v0.0.0-synthetic" for e in store.snapshot(environment="test"))


def test_report_returns_no_event_or_visit_identifiers(sample):
    import json

    _, store, _ = sample
    events = store.snapshot(environment="test")
    serialized = json.dumps(report(events))
    assert all(str(e.event_id) not in serialized and str(e.game_session_id) not in serialized for e in events)


@pytest.mark.parametrize("kwargs", [{"mode": "combined"}, {"environment": "invalid"}, {"as_of": "yesterday"}])
def test_invalid_report_cohort_or_timestamp(kwargs):
    with pytest.raises(ValueError):
        build_report([], **kwargs)


def test_inflight_hint_requested_before_terminal_still_counts():
    start = event()
    request = event("hint_requested", number=2, sequence=2)
    reveal = event("solution_revealed", number=3, sequence=3)
    delivery = event("hint_delivered", number=4, sequence=4, properties={"attempt_id": uid(2), "pre_terminal": True, "hint_number": 1})
    assert report([start, request, reveal, delivery])["summary"]["hints_delivered"] == 1


def test_question_submitted_after_terminal_is_a_consistency_issue():
    result = report([event(), event("solution_revealed", number=2, sequence=2),
                     event("question_submitted", number=3, sequence=3)])
    assert result["summary"]["unclassified_games"] == 1
    assert result["summary"]["reveal_rate"] == 0


@pytest.mark.parametrize("count,low_sample", [(19, True), (20, False)])
def test_mystery_sample_threshold(count, low_sample):
    result = report([event(number=i+1, game=1000+i) for i in range(count)])
    assert result["mysteries"][0]["low_sample"] is low_sample
