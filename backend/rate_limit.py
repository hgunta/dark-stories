"""Process-local, bounded sliding-window admission for paid-action protection.

No IP tracking, cookies, persistent identifiers, raw prompts, or logging.
One lock makes multi-bucket admission atomic; denied requests use no quota.
"""
from collections import deque
import math
from threading import Lock
import time


class RequestLimiter:
    WINDOW_SECONDS = 60
    ROOM_CREATES_PER_MINUTE = 30
    QUESTIONS_PER_ROOM_PER_MINUTE = 15
    QUESTIONS_GLOBAL_PER_MINUTE = 120

    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self._lock = Lock()
        self._buckets = {}

    def _admit(self, specs):
        """Return (allowed, retry_after_seconds) under a common clock."""
        with self._lock:
            now = self.clock()
            window = self.WINDOW_SECONDS
            # Expire the whole key, not just individual timestamps, so even
            # inactive room keys do not accumulate indefinitely.
            for key, values in list(self._buckets.items()):
                while values and now - values[0] >= window:
                    values.popleft()
                if not values:
                    del self._buckets[key]

            blocked = []
            for key, quota in specs:
                values = self._buckets.get(key)
                if values is not None and len(values) >= quota:
                    blocked.append(max(1, math.ceil(window - (now - values[0]))))
            if blocked:
                return False, max(blocked)

            for key, _ in specs:
                self._buckets.setdefault(key, deque()).append(now)
            return True, 0

    def allow_create(self):
        return self._admit((("create", self.ROOM_CREATES_PER_MINUTE),))

    def allow_question(self, room_id):
        # Caller must have resolved a live room. Shared global quota prevents
        # circumventing limits by opening many different rooms.
        return self._admit((
            ("questions_global", self.QUESTIONS_GLOBAL_PER_MINUTE),
            (("question_room", room_id), self.QUESTIONS_PER_ROOM_PER_MINUTE),
        ))
