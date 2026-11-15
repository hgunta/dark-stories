"""Bounded, process-local post-game feedback MVP. Not durable on Render.

Ratings, issue codes and optional bounded comments are temporary.
Never treat comments as chat transcripts or training data.
"""

from threading import Lock

ISSUES = frozenset({"none", "confusing_clues", "incorrect_answer", "spoiler", "other"})


class FeedbackStore:
    def __init__(self, capacity=2000):
        self._lock = Lock()
        self._items = {}
        self.capacity = capacity

    def submit(self, room_id, mystery_id, rating, issue, note=""):
        with self._lock:
            if room_id in self._items:
                return "duplicate"
            if len(self._items) >= self.capacity:
                return "full"
            # Keys never become a public reporting interface.
            self._items[room_id] = {"mystery_id": mystery_id, "rating": rating, "issue": issue, "note": note[:500]}
            return "created"

    def add_details(self, room_id, rating, issue, note=""):
        """Attach optional follow-up once, after the star rating is saved."""
        with self._lock:
            item = self._items.get(room_id)
            if item is None or item["rating"] != rating:
                return "missing"
            if item["issue"] != "none" or item["note"]:
                return "duplicate"
            if issue == "none" and not note:
                return "duplicate"
            if issue not in ISSUES:
                raise ValueError("invalid feedback issue")
            item["issue"] = issue
            item["note"] = note[:500]
            return "updated"


    def count(self):
        with self._lock:
            return len(self._items)
