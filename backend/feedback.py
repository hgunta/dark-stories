"""Bounded, process-local post-game feedback MVP. Not durable on Render.

Only structured codes are retained. Never accept free-text, player identities,
questions, answers, hints, or private mystery contents.
"""

from threading import Lock

ISSUES = frozenset({"none", "confusing_clues", "incorrect_answer", "spoiler", "other"})


class FeedbackStore:
    def __init__(self, capacity=2000):
        self._lock = Lock()
        self._items = {}
        self.capacity = capacity

    def submit(self, room_id, mystery_id, rating, issue):
        with self._lock:
            if room_id in self._items:
                return "duplicate"
            if len(self._items) >= self.capacity:
                return "full"
            # Keys never become a public reporting interface.
            self._items[room_id] = {"mystery_id": mystery_id, "rating": rating, "issue": issue}
            return "created"

    def count(self):
        with self._lock:
            return len(self._items)
