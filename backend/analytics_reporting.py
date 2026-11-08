"""Pure aggregate reporting over validated events; no collection or user data."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from pydantic import TypeAdapter

from .analytics import UTCTimestamp, validate_event
from .analytics_storage import ENVIRONMENTS, _semantic_key

SYNTHETIC_REVISION = "v0.0.0-synthetic"
LIMITATIONS = [
    "Local development report, not production analytics or a count of unique people.",
    "Rates use starts at least 30 minutes old; unresolved and unclassified mature games remain in the denominator.",
    "Attempts/hints use the selected start-mode cohort and selected action mode; zero-question starts remain in averages.",
    "Sequence gaps, unmatched responses and missing starts indicate incomplete capture; unknown completion is not abandonment.",
    "Mixed-mode, inconsistent, or ambiguous games have no classified terminal outcome; rates may understate completion.",
    "Browser delivery, restart losses and recorder drops cannot be fully measured from stored events.",
    "Abandonment and replay rates are unavailable: inactivity reconciliation and browser visits are not implemented.",
    "Mystery rows below 20 mature starts are descriptive samples, not reliable difficulty rankings.",
]


def _deduplicate(events):
    by_id = defaultdict(list)
    for event in events:
        event = validate_event(event)
        by_id[event.event_id].append(event)
    result, quality, blocked = [], Counter(), set()
    for group in by_id.values():
        if any(e != group[0] for e in group[1:]):
            quality["conflicting_event_ids"] += 1
            blocked.update(e.game_session_id for e in group)
        else:
            quality["duplicate_rows_ignored"] += len(group) - 1
            result.append(group[0])
    by_key = defaultdict(list)
    for event in result:
        by_key[_semantic_key(event)].append(event)
    result = []
    for group in by_key.values():
        first = group[0].model_dump(exclude={"event_id"})
        if any(e.model_dump(exclude={"event_id"}) != first for e in group[1:]):
            quality["conflicting_semantic_keys"] += 1
            blocked.update(e.game_session_id for e in group)
        else:
            quality["duplicate_rows_ignored"] += len(group) - 1
            result.append(group[0])
    return result, quality, blocked


def _summarize(games):
    starts = len(games)
    mature = [g for g in games if g["mature"]]
    total = lambda field: sum(g[field] for g in games)
    solved = sum(g["outcome"] == "solved" for g in mature)
    revealed = sum(g["outcome"] == "revealed" for g in mature)
    return dict(
        game_starts=starts, engaged_games=sum(g["attempts"] > 0 for g in games),
        question_attempts=total("attempts"), question_responses=total("responses"),
        average_question_attempts=total("attempts") / starts if starts else None,
        hints_delivered=total("hints"), average_hints_delivered=total("hints") / starts if starts else None,
        mature_games=len(mature), immature_games=starts-len(mature),
        solved_games=solved, revealed_games=revealed,
        solve_rate=solved / len(mature) if mature else None,
        reveal_rate=revealed / len(mature) if mature else None,
        unresolved_games=sum(g["outcome"] == "unresolved" for g in games),
        unclassified_games=sum(g["outcome"] == "unclassified" for g in games),
    )


def build_report(events, *, environment="test", mode="ai", as_of=None):
    """Report one environment/start-mode cohort at an explicit UTC cutoff.

    Input duplication is defensively reconciled even though SQLite rejects it.
    No IDs, timestamps of individual games, or raw event properties are returned.
    """
    if environment not in ENVIRONMENTS or mode not in ("ai", "offline"):
        raise ValueError("unknown report cohort")
    if as_of is None:
        now = datetime.now(timezone.utc)
        as_of = now.replace(microsecond=now.microsecond // 1000 * 1000)
    as_of = TypeAdapter(UTCTimestamp).validate_python(as_of)
    events, quality, blocked = _deduplicate(events)
    relevant = [e for e in events if e.environment == environment]
    synthetic = bool(relevant) and all(e.app_revision == SYNTHETIC_REVISION for e in relevant)
    quality["future_events_excluded"] = sum(e.occurred_at > as_of or e.recorded_at > as_of for e in relevant)
    relevant = [e for e in relevant if e.occurred_at <= as_of and e.recorded_at <= as_of]
    groups = defaultdict(list)
    for event in relevant:
        if event.game_session_id is None:
            quality["unassociated_errors"] += 1
        else:
            groups[event.game_session_id].append(event)
    games = []
    for game_id, group in groups.items():
        group.sort(key=lambda e: (e.game_sequence, str(e.event_id)))
        starts = [e for e in group if e.event_name == "game_started"]
        if len(starts) != 1:
            quality["events_without_unique_start"] += len(group)
            continue
        start = starts[0]
        if start.mode != mode:
            continue
        bad = game_id in blocked
        sequences = {e.game_sequence for e in group}
        if min(sequences) != 1 or max(sequences) != len(sequences) or len(sequences) != len(group):
            quality["games_with_sequence_gaps_or_collisions"] += 1
            bad = True
        if start.game_sequence != 1 or any(e.mystery_id != start.mystery_id or
                e.content_revision != start.content_revision for e in group):
            quality["games_with_identity_conflicts"] += 1
            bad = True
        if any(e.mode != mode for e in group):
            quality["mixed_mode_games"] += 1
            bad = True
        if start.browser_visit_id is None:
            quality["games_without_browser_visit"] += 1
        selected = [e for e in group if e.mode == mode]
        questions = {e.properties.attempt_id: e for e in selected if e.event_name == "question_submitted"}
        answers = {e.properties.attempt_id: e for e in selected if e.event_name == "question_answered"}
        matched = {key: e for key, e in answers.items() if key in questions and
                   questions[key].game_sequence < e.game_sequence}
        quality["orphan_or_misordered_question_responses"] += len(answers)-len(matched)
        quality["unanswered_question_attempts"] += len(questions.keys()-matched.keys())
        failed = {e.properties.attempt_id for e in selected if e.event_name == "game_error" and
                  e.properties.stage == "processing" and e.properties.operation == "message"}
        quality["unknown_question_completions"] += len(questions.keys()-matched.keys()-failed)
        terminals = [e for e in selected if e.event_name == "game_solved" or
                     (e.event_name == "solution_revealed" and e.properties.establishes_outcome)]
        terminal = terminals[0] if len(terminals) == 1 else None
        terminal_issue = len(terminals) > 1
        if terminal and terminal.event_name == "game_solved":
            answer = matched.get(terminal.properties.attempt_id)
            terminal_issue |= answer is None or answer.properties.response_category != "solved" or answer.game_sequence >= terminal.game_sequence
        if terminal:
            terminal_issue |= terminal.game_sequence <= start.game_sequence
            terminal_issue |= any(q.game_sequence >= terminal.game_sequence for q in questions.values())
        for e in selected:
            if e.event_name == "solution_revealed" and not e.properties.establishes_outcome:
                terminal_issue |= terminal is None or terminal.game_sequence >= e.game_sequence
        solved_answers = {key for key, e in matched.items() if e.properties.response_category == "solved"}
        if solved_answers and (terminal is None or terminal.event_name != "game_solved" or
                               solved_answers != {terminal.properties.attempt_id}):
            terminal_issue = True
        if terminal_issue:
            quality["games_with_terminal_issues"] += 1
            bad = True
        requests = {e.properties.attempt_id: e for e in selected if e.event_name == "hint_requested"}
        hints = 0
        for e in selected:
            if e.event_name != "hint_delivered":
                continue
            request = requests.get(e.properties.attempt_id)
            if request is None or request.game_sequence >= e.game_sequence or request.properties.pre_terminal != e.properties.pre_terminal:
                quality["orphan_or_misordered_hint_deliveries"] += 1
            elif e.properties.pre_terminal and (terminal is None or request.game_sequence < terminal.game_sequence):
                hints += 1
        quality["abandonment_events_not_interpreted"] += sum(e.event_name == "game_abandoned" for e in selected)
        outcome = ("unclassified" if bad else "unresolved" if terminal is None else
                   "solved" if terminal.event_name == "game_solved" else "revealed")
        games.append(dict(mystery_id=start.mystery_id, content_revision=start.content_revision,
                          mature=as_of-start.occurred_at >= timedelta(minutes=30),
                          attempts=len(questions), responses=len(matched), hints=hints, outcome=outcome))
    mysteries = defaultdict(list)
    for game in games:
        mysteries[(game["mystery_id"], game["content_revision"])].append(game)
    quality_keys = ["duplicate_rows_ignored", "conflicting_event_ids", "conflicting_semantic_keys",
                    "future_events_excluded", "unassociated_errors", "events_without_unique_start",
                    "games_with_sequence_gaps_or_collisions", "games_with_identity_conflicts", "mixed_mode_games",
                    "games_without_browser_visit", "orphan_or_misordered_question_responses",
                    "unanswered_question_attempts", "unknown_question_completions",
                    "orphan_or_misordered_hint_deliveries", "games_with_terminal_issues", "abandonment_events_not_interpreted"]
    return dict(
        environment=environment, mode=mode, as_of=as_of.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        dataset_label="Synthetic sample data" if synthetic else "Local data (not verified synthetic)",
        summary=_summarize(games),
        mysteries=[dict(mystery_id=key[0], content_revision=key[1], **_summarize(items),
                        low_sample=sum(g["mature"] for g in items) < 20)
                   for key, items in sorted(mysteries.items(), key=lambda pair: (pair[0][0], pair[0][1] or ""))],
        coverage={key: quality[key] for key in quality_keys}, events_loaded=len(relevant),
        abandonment_rate=None, replay_rate=None, limitations=LIMITATIONS,
    )
