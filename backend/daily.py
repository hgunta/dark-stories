"""Deterministic UTC daily selection and transparent score.

The current curated catalog has only three mysteries, so the daily selection
necessarily repeats; never imply it is fresh content every day.
"""
from datetime import date, datetime, timezone

EPOCH = date(2026, 11, 1)


def utc_today():
    return datetime.now(timezone.utc).date()


def challenge_for(day, catalog):
    if not catalog:
        raise ValueError("daily challenge requires published mysteries")
    entries = sorted(catalog, key=lambda m: m["id"])
    index = (day - EPOCH).days % len(entries)
    selected = entries[index]
    return {
        "date": day.isoformat(),
        "mystery_id": selected["id"],
        "title": selected["title"],
        "reset_timezone": "UTC",
    }


def daily_score(*, solved, revealed, questions, hints, wrong_guesses):
    # A revealed answer earns no solve score; a legitimate solve gets at least
    # 10 points. Values are per-game metrics, not user identities.
    if not solved or revealed:
        return 0
    return max(10, 100 - 5 * questions - 15 * hints - 10 * wrong_guesses)


def daily_result(room):
    day = room.get("daily_date")
    if day is None:
        return None
    state = room["state"]
    end = room.get("daily_outcome")
    questions = room.get("daily_questions", 0)
    wrong_guesses = room.get("daily_wrong_guesses", 0)
    hints = state["hints_used"]
    return {
        "date": day,
        "mystery_id": room["mystery"]["mystery_id"],
        "completed": end is not None,
        "outcome": end,
        "questions": questions,
        "hints": hints,
        "wrong_guesses": wrong_guesses,
        "score": daily_score(
            solved=end == "solved", revealed=end == "revealed",
            questions=questions, hints=hints, wrong_guesses=wrong_guesses
        ) if end else None,
    }
