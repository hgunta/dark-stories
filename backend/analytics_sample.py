"""Generate labeled synthetic test events only, never real gameplay or API calls."""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from .analytics import validate_event
from .analytics_reporting import SYNTHETIC_REVISION
from .analytics_storage import SQLiteEventStore


def generate_sample(database_path, *, now=None):
    """Refuse existing files; no overwrites and no implicit parent-directory creation."""
    path = Path(database_path).resolve()
    # Reserve the requested filename atomically; never truncate an existing DB.
    with path.open("xb"):
        pass
    try:
        store = SQLiteEventStore(path)
        store.initialize()
        now = now or datetime.now(timezone.utc)
        now = now.replace(microsecond=now.microsecond // 1000 * 1000)
        serial = 0
        count = 0

        def identifier():
            nonlocal serial
            serial += 1
            return UUID(int=serial, version=4)

        for number, mystery, mode, age, outcome in [
            (1, "ms-001", "ai", 120, "solved"),
            (2, "ms-002", "ai", 110, "revealed"),
            (3, "ms-001", "ai", 100, "missing_answer"),
            (4, "ms-003", "offline", 90, "revealed"),
            (5, "ms-003", "ai", 5, "recent"),
            (6, "ms-002", "ai", 80, "zero_questions"),
        ]:
            game = UUID(int=10000+number, version=4)
            sequence = 0
            started = now-timedelta(minutes=age)

            def emit(name, properties):
                nonlocal count, sequence
                sequence += 1
                at = started+timedelta(seconds=sequence-1)
                event = validate_event(dict(
                    schema_version=1, event_name=name, event_id=identifier(), environment="test",
                    source="server", occurred_at=at, recorded_at=at, game_session_id=game,
                    mystery_id=mystery, browser_visit_id=None, mode=mode, game_sequence=sequence,
                    app_revision=SYNTHETIC_REVISION, properties=properties,
                ))
                store.insert(event)
                count += 1

            emit("game_started", {"start_source": "unknown"})
            if outcome in ("recent", "zero_questions"):
                continue
            attempt = identifier()
            emit("question_submitted", {"attempt_id": attempt})
            if outcome == "missing_answer":
                continue
            emit("question_answered", dict(attempt_id=attempt, response_category="unknown" if mode == "offline" else "no",
                 response_origin="offline_stub" if mode == "offline" else "ai_tool"))
            hint = identifier()
            emit("hint_requested", dict(attempt_id=hint, pre_terminal=True))
            emit("hint_delivered", dict(attempt_id=hint, pre_terminal=True, hint_number=1))
            if outcome == "solved":
                attempt = identifier()
                emit("question_submitted", {"attempt_id": attempt})
                emit("question_answered", dict(attempt_id=attempt, response_category="solved", response_origin="ai_tool"))
                emit("game_solved", dict(attempt_id=attempt, solve_method="moderator_label"))
            else:
                emit("solution_revealed", dict(attempt_id=identifier(), establishes_outcome=True))
            emit("solution_revealed", dict(attempt_id=identifier(), establishes_outcome=False))
        return count
    except Exception:
        path.unlink(missing_ok=True)  # Only the file exclusively created above.
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create SYNTHETIC test analytics in a NEW local SQLite file")
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args(argv)
    count = generate_sample(args.database)
    print(f"SYNTHETIC SAMPLE ONLY: {count} events in {args.database.resolve()}; no player data or API calls")


if __name__ == "__main__":
    main()
