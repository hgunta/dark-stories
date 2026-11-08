"""Small bounded public timeline for same-process collaborative rooms.

This is not a private-guess interface: only explicitly public activity belongs
in this feed. Never mirror the solution summary or moderator private facts.
"""

MAX_PUBLIC_EVENTS = 100
MAX_PUBLIC_QUESTION_CHARS = 400


def append_public(room, kind, *, question=None, reply=None):
    if kind not in {"question", "hint", "solved", "revealed"}:
        raise ValueError("invalid public event")
    entry = {"seq": room.get("next_public_seq", 1), "kind": kind}
    if kind == "question":
        if not isinstance(question, str):
            raise ValueError("public question required")
        entry["question"] = question[:MAX_PUBLIC_QUESTION_CHARS]
        entry["reply"] = reply if reply in {
            "Yes", "No", "Irrelevant", "Unknown", "Ask a Yes/No question"
        } else "Moderator responded"
    elif kind == "hint":
        if not isinstance(reply, str):
            raise ValueError("hint text required")
        entry["reply"] = reply
    # Solved/revealed are public outcomes but NEVER include solution content.
    room.setdefault("public_events", []).append(entry)
    room["next_public_seq"] = entry["seq"] + 1
    if len(room["public_events"]) > MAX_PUBLIC_EVENTS:
        del room["public_events"][:-MAX_PUBLIC_EVENTS]
    return entry


def public_snapshot(room):
    return {
        "room_code": room["code"],
        "mystery_id": room["mystery"]["mystery_id"],
        "title": room["mystery"]["title"],
        "premise": room["mystery"]["premise_public"],
        "solved": room["state"]["solved"],
        "hints_used": room["state"]["hints_used"],
        "last_seq": room.get("next_public_seq", 1) - 1,
        "events": [dict(event) for event in room.get("public_events", [])],
    }
