"""Explicit local SQLite event storage; never imported or enabled by gameplay."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from pydantic import TypeAdapter

from .analytics import AnalyticsEvent, EventEnvelope, EventUUID, UTCTimestamp, validate_event

EVENT_NAMES = frozenset({
    "game_started", "question_submitted", "question_answered", "hint_requested",
    "hint_delivered", "game_solved", "solution_revealed", "game_abandoned", "game_error",
})
ENVIRONMENTS = frozenset({"production", "staging", "local", "test"})
_UUID = TypeAdapter(EventUUID)
_TIME = TypeAdapter(UTCTimestamp)


class EventConflictError(ValueError):
    """An ID, semantic key, sequence, or terminal assertion conflicts with storage."""


def _semantic_key(event):
    data = event.model_dump(mode="json")
    key = [event.environment, data["game_session_id"], event.event_name]
    if event.event_name == "game_abandoned":
        key.extend([data["properties"]["last_activity_at"], event.properties.rule_version])
    elif event.event_name == "game_error":
        key = [event.environment, event.event_name, str(event.properties.attempt_id)]
    elif event.event_name != "game_started":
        key.append(str(event.properties.attempt_id))
    return json.dumps(key, separators=(",", ":"))


class SQLiteEventStore:
    """No connection or file is created until initialize() is explicitly called.

    Each operation owns a connection, so independent threads/store instances can
    compete safely without sharing connection objects. This is a local adapter,
    not a claim of Render durability or an exactly-once collection system.
    """

    def __init__(self, database_path: str | Path):
        if not isinstance(database_path, (str, Path)) or not str(database_path).strip():
            raise ValueError("an explicit database file path is required")
        if str(database_path) == ":memory:" or str(database_path).startswith("file:"):
            raise ValueError("supply a file path, not a SQLite URI or in-memory name")
        self.path = Path(database_path).resolve()

    @contextmanager
    def _connection(self, *, create=False):
        # URI encoding preserves literal special characters in explicit paths.
        mode = "rwc" if create else "rw"
        connection = sqlite3.connect(f"{self.path.as_uri()}?mode={mode}", uri=True,
                                     timeout=5.0, isolation_level=None)
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create version-1 tables/indexes atomically; never create parent dirs."""
        with self._connection(create=True) as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported analytics database version")
            db.execute("""CREATE TABLE IF NOT EXISTS analytics_events (
                event_id TEXT PRIMARY KEY NOT NULL,
                environment TEXT NOT NULL,
                game_session_id TEXT,
                game_sequence INTEGER,
                event_name TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                semantic_key TEXT NOT NULL UNIQUE,
                terminal INTEGER NOT NULL CHECK (terminal IN (0, 1)),
                payload TEXT NOT NULL,
                UNIQUE(environment, game_session_id, game_sequence)
            )""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS analytics_terminal
                ON analytics_events(environment, game_session_id) WHERE terminal = 1""")
            db.execute("""CREATE INDEX IF NOT EXISTS analytics_game
                ON analytics_events(environment, game_session_id, game_sequence)""")
            db.execute("""CREATE INDEX IF NOT EXISTS analytics_name_time
                ON analytics_events(environment, event_name, occurred_at, event_id)""")
            db.execute("""CREATE INDEX IF NOT EXISTS analytics_time
                ON analytics_events(environment, occurred_at, event_id)""")
            db.execute("""CREATE INDEX IF NOT EXISTS analytics_recorded
                ON analytics_events(environment, recorded_at)""")
            db.execute("PRAGMA user_version = 1")
            db.commit()

    def insert(self, event: AnalyticsEvent) -> bool:
        """True on insertion; False for an exact canonical retry; conflict raises.

        Raw dicts/JSON are not accepted. Revalidate models to catch trusted-copy
        or construction bypasses before opening a connection or writing data.
        """
        if not isinstance(event, EventEnvelope):
            raise TypeError("insert requires a validated analytics event model")
        event = validate_event(event)
        data = event.model_dump(mode="json")
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        terminal = event.event_name == "game_solved" or (
            event.event_name == "solution_revealed" and event.properties.establishes_outcome)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT payload FROM analytics_events WHERE event_id = ?",
                               (str(event.event_id),)).fetchone()
            if prior is not None:
                if prior[0] != payload:
                    raise EventConflictError("event ID has a conflicting payload")
                db.commit()
                return False
            if event.event_name == "solution_revealed" and not terminal:
                prior_terminal = db.execute("""SELECT game_sequence FROM analytics_events
                    WHERE environment = ? AND game_session_id = ? AND terminal = 1""",
                    (event.environment, data["game_session_id"])).fetchone()
                if prior_terminal is None or prior_terminal[0] >= event.game_sequence:
                    raise EventConflictError("nonterminal reveal requires an earlier terminal outcome")
            try:
                db.execute("""INSERT INTO analytics_events
                    (event_id, environment, game_session_id, game_sequence, event_name,
                     occurred_at, recorded_at, semantic_key, terminal, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(event.event_id), event.environment, data["game_session_id"],
                     event.game_sequence, event.event_name, data["occurred_at"],
                     data["recorded_at"], _semantic_key(event), int(terminal), payload))
            except sqlite3.IntegrityError:
                raise EventConflictError("event violates a storage uniqueness or integrity constraint") from None
            db.commit()
        return True

    def get(self, event_id, *, environment: str) -> AnalyticsEvent | None:
        _environment(environment)
        event_id = str(_UUID.validate_python(event_id))
        with self._connection() as db:
            row = db.execute("""SELECT payload FROM analytics_events
                WHERE event_id = ? AND environment = ?""", (event_id, environment)).fetchone()
        return validate_event(row[0]) if row else None

    def read(self, *, environment: str, game_session_id=None, event_name=None,
             since=None, until=None, limit=100, offset=0) -> list[AnalyticsEvent]:
        """Bounded reads: [since, until), UTC; game sequence or global time order.

        Pagination is for a static snapshot only: concurrent inserts can move
        offset pages. No raw SQL, column name, or arbitrary filter is accepted.
        """
        _environment(environment)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        if type(offset) is not int or not 0 <= offset <= 100000:
            raise ValueError("offset must be an integer from 0 to 100000")
        clauses, values = ["environment = ?"], [environment]
        if game_session_id is not None:
            clauses.append("game_session_id = ?")
            values.append(str(_UUID.validate_python(game_session_id)))
        if event_name is not None:
            if not isinstance(event_name, str) or event_name not in EVENT_NAMES:
                raise ValueError("unknown event name")
            clauses.append("event_name = ?")
            values.append(event_name)
        lower = _TIME.validate_python(since) if since is not None else None
        upper = _TIME.validate_python(until) if until is not None else None
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError("since must precede until")
        for column_op, value in [("occurred_at >= ?", lower), ("occurred_at < ?", upper)]:
            if value is not None:
                clauses.append(column_op)
                values.append(value.isoformat(timespec="milliseconds").replace("+00:00", "Z"))
        order = "game_sequence, event_id" if game_session_id is not None else "occurred_at, event_id"
        # All interpolated fragments are internal constants, never caller SQL.
        query = "SELECT payload FROM analytics_events WHERE " + " AND ".join(clauses)
        query += " ORDER BY " + order + " LIMIT ? OFFSET ?"
        with self._connection() as db:
            rows = db.execute(query, (*values, limit, offset)).fetchall()
        return [validate_event(row[0]) for row in rows]


def _environment(value):
    if not isinstance(value, str) or value not in ENVIRONMENTS:
        raise ValueError("unknown environment")
