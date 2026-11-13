"""Bounded, process-local post-game feedback MVP. Not durable on Render.

Ratings, issue codes and optional bounded feedback comments are temporary.
Never use these comments as game transcripts or training data.
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

    def count(self):
        with self._lock:
            return len(self._items)
