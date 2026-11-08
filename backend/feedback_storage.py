"""Explicit SQLite feedback store. Local/durable only when supplied a durable path.

No raw room ID, messages, answers, or free-text fields are persisted.
The normal production app does not instantiate this store.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3

from .feedback import ISSUES

_MYSTERY = re.compile(r"ms-[0-9]{3,8}\Z")
_RETENTION_DAYS = 30


class SQLiteFeedbackStore:
    def __init__(self, database_path):
        if not isinstance(database_path, (str, Path)) or not str(database_path).strip():
            raise ValueError("explicit database path required")
        if str(database_path) == ":memory:" or str(database_path).startswith("file:"):
            raise ValueError("SQLite URI and memory names not supported")
        self.path = Path(database_path).resolve()

    def _connect(self, *, readonly=False):
        mode = "ro" if readonly else "rw"
        return sqlite3.connect(f"{self.path.as_uri()}?mode={mode}", uri=True, timeout=1.0)

    def initialize(self):
        """Creates database only at explicit path; never parent directories."""
        with sqlite3.connect(f"{self.path.as_uri()}?mode=rwc", uri=True, timeout=1.0) as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported feedback database version")
            db.execute("""CREATE TABLE IF NOT EXISTS feedback_meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS feedback (
                room_digest TEXT PRIMARY KEY,
                mystery_id TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                issue TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS feedback_time ON feedback(created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS feedback_mystery ON feedback(mystery_id)")
            db.execute("INSERT OR IGNORE INTO feedback_meta(key, value) VALUES ('salt', ?)",
                       (secrets.token_hex(32),))
            db.execute("PRAGMA user_version = 1")

    def submit(self, room_id, mystery_id, rating, issue):
        if not isinstance(room_id, str) or not room_id or len(room_id) > 128:
            raise ValueError("invalid room identifier")
        if not isinstance(mystery_id, str) or not _MYSTERY.fullmatch(mystery_id):
            raise ValueError("invalid mystery identifier")
        if type(rating) is not int or not 1 <= rating <= 5 or issue not in ISSUES:
            raise ValueError("invalid feedback")
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            salt = db.execute("SELECT value FROM feedback_meta WHERE key = 'salt'").fetchone()
            if salt is None:
                raise ValueError("uninitialized feedback database")
            digest = hmac.new(bytes.fromhex(salt[0]), room_id.encode("utf-8"), hashlib.sha256).hexdigest()
            prior = db.execute("SELECT 1 FROM feedback WHERE room_digest = ?", (digest,)).fetchone()
            if prior:
                return "duplicate"
            db.execute("""INSERT INTO feedback
                (room_digest, mystery_id, rating, issue, created_at)
                VALUES (?, ?, ?, ?, ?)""", (digest, mystery_id, rating, issue, now))
        return "created"

    def count(self):
        with self._connect(readonly=True) as db:
            return db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]

    def summarize(self):
        """Aggregate-only owner export. No room digests or individual records."""
        with self._connect(readonly=True) as db:
            db.execute("BEGIN")
            overall = db.execute("SELECT COUNT(*), AVG(rating) FROM feedback").fetchone()
            by_rating = db.execute(
                "SELECT rating, COUNT(*) FROM feedback GROUP BY rating ORDER BY rating").fetchall()
            by_issue = db.execute(
                "SELECT issue, COUNT(*) FROM feedback GROUP BY issue ORDER BY issue").fetchall()
            by_mystery = db.execute("""SELECT mystery_id, COUNT(*), AVG(rating)
                FROM feedback GROUP BY mystery_id ORDER BY mystery_id""").fetchall()
        return {
            "total": overall[0],
            "average_rating": round(overall[1], 2) if overall[1] is not None else None,
            "ratings": {str(k): v for k, v in by_rating},
            "issues": {k: v for k, v in by_issue},
            "mysteries": [{"mystery_id": k, "count": n, "average_rating": round(avg, 2)}
                          for k, n, avg in by_mystery],
        }

    def delete_expired(self, *, days=_RETENTION_DAYS, now=None):
        """Explicit owner-run cleanup, not an automatic retention guarantee."""
        if type(days) is not int or days < 1:
            raise ValueError("days must be positive")
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            raise ValueError("now must have timezone")
        cutoff = (moment.astimezone(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("DELETE FROM feedback WHERE created_at < ?", (cutoff,))
            return result.rowcount
