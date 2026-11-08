"""Opt-in, local/test-only gameplay instrumentation; no environment activation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from threading import RLock
from uuid import uuid4

if __package__:
    from .analytics import validate_event
else:  # uvicorn app:app --app-dir backend
    from analytics import validate_event


def _utc_now():
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def _fail_open(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        if not self.enabled:
            return None
        try:
            with self._lock:
                return method(self, *args, **kwargs)
        except Exception:
            # Never log exceptions, input, schema diagnostics, or game content.
            self.dropped = min(self.dropped + 1, 2**31 - 1)
            return None
    return guarded


@dataclass
class _Game:
    room: dict  # Retain identity, not a copy; never serialized.
    game_id: object
    mystery_id: str
    sequence: int = 0
    started: bool = False
    terminal: bool = False


@dataclass
class _Attempt:
    game_id: object
    attempt_id: object
    mode: str
    pre_terminal: bool
    closed: bool = False


class AnalyticsRecorder:
    """Configure explicitly with enabled=True, an initialized store, and test/local.

    No file paths, environment flags, initialization, background work, or logs.
    Production/staging activation is deliberately unsupported in this increment.
    """

    def __init__(self, store=None, *, enabled=False, environment=None,
                 clock=_utc_now, id_factory=uuid4):
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        if enabled and (store is None or environment not in ("test", "local")):
            raise ValueError("enabled instrumentation requires an explicit local/test store")
        self.enabled = enabled
        self.store = store
        self.environment = environment
        self._clock, self._id = clock, id_factory
        self._games = {}
        self._lock = RLock()
        self.dropped = 0

    def _emit(self, name, game, mode, properties):
        now = self._clock()
        if game is not None:
            game.sequence += 1
        event = validate_event(dict(
            schema_version=1, event_name=name, event_id=self._id(),
            environment=self.environment, source="server", occurred_at=now, recorded_at=now,
            game_session_id=game.game_id if game else None,
            mystery_id=game.mystery_id if game else None, browser_visit_id=None,
            mode=mode, game_sequence=game.sequence if game else None, properties=properties,
        ))
        self.store.insert(event)

    def _game(self, room):
        game = self._games.get(id(room))
        return game if game is not None and game.started else None

    @_fail_open
    def start(self, room, mode):
        if id(room) in self._games:
            return
        game = _Game(room, self._id(), room["mystery"]["mystery_id"])
        self._games[id(room)] = game
        self._emit("game_started", game, mode, {"start_source": "unknown"})
        game.started = True

    @_fail_open
    def question(self, room, mode):
        game = self._game(room)
        if game is None or game.terminal:
            return None
        attempt = _Attempt(game.game_id, self._id(), mode, True)
        self._emit("question_submitted", game, mode, {"attempt_id": attempt.attempt_id})
        return attempt

    @_fail_open
    def answered(self, room, attempt, category, origin, solve_method=None):
        game = self._game(room)
        if game is None or attempt is None or attempt.closed or attempt.game_id != game.game_id:
            return
        attempt.closed = True
        establishes = solve_method is not None and not game.terminal
        if establishes:
            game.terminal = True  # Do not turn lost solves into later reveal outcomes.
        self._emit("question_answered", game, attempt.mode, dict(
            attempt_id=attempt.attempt_id, response_category=category, response_origin=origin))
        if establishes:
            self._emit("game_solved", game, attempt.mode,
                       dict(attempt_id=attempt.attempt_id, solve_method=solve_method))

    @_fail_open
    def hint_requested(self, room, mode):
        game = self._game(room)
        if game is None:
            return None
        attempt = _Attempt(game.game_id, self._id(), mode, not room["state"]["solved"])
        self._emit("hint_requested", game, mode,
                   dict(attempt_id=attempt.attempt_id, pre_terminal=attempt.pre_terminal))
        return attempt

    @_fail_open
    def hint_delivered(self, room, attempt, number):
        game = self._game(room)
        if game is None or attempt is None or attempt.closed or attempt.game_id != game.game_id:
            return
        attempt.closed = True
        self._emit("hint_delivered", game, attempt.mode, dict(
            attempt_id=attempt.attempt_id, hint_number=number, pre_terminal=attempt.pre_terminal))

    @_fail_open
    def revealed(self, room, mode, was_solved):
        game = self._game(room)
        if game is None:
            return
        establishes = not was_solved and not game.terminal
        if establishes:
            game.terminal = True
        self._emit("solution_revealed", game, mode, dict(
            attempt_id=self._id(), establishes_outcome=establishes))

    @_fail_open
    def error(self, operation, code, mode, *, room=None, attempt=None, http_status=None):
        game = self._game(room) if room is not None else None
        if attempt is not None and attempt.closed:
            return
        if attempt is not None:
            attempt.closed = True
        properties = dict(attempt_id=attempt.attempt_id if attempt else self._id(),
                          operation=operation, error_code=code,
                          stage="processing" if attempt else "before_acceptance")
        if http_status is not None:
            properties["http_status"] = http_status
        self._emit("game_error", game, attempt.mode if attempt else mode, properties)
