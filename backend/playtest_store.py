"""Preview-only, privacy-bounded Postgres playtest data.

No network or database connection at import time. The app instantiates this
only with an explicit preview database URL and enabled flag. Do not log DSNs,
user text or receipt tokens. All reads/writes are parameterized.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
import secrets
import threading
from uuid import uuid4

import psycopg

CASE_ID = re.compile(r"^ex-[0-9]{3}$")
SAFE_ISSUES = frozenset({"none", "confusing_clues", "incorrect_answer", "spoiler", "other"})
KINDS = frozenset({"question", "private_guess", "hint", "reveal"})
LABELS = frozenset({"yes", "no", "unknown", "irrelevant", "ask_yes_no",
                    "almost_solved", "solved", "hint", "revealed"})
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\w)")
_URL = re.compile(r"https?://\S+", re.I)
# Not a guarantee of anonymity: reviewers must independently vet content.
def redact(value):
    text = value[:1000] if isinstance(value, str) else ""
    return _PHONE.sub("[PHONE]", _EMAIL.sub("[EMAIL]", _URL.sub("[URL]", text)))

class PlaytestStore:
    """One session contains ONLY case/version + bounded event counts by default.

    Transcript rows are written only when the same session has opted in and
    has not been disabled after a multiplayer join or revocation.
    """
    def __init__(self, dsn):
        if not isinstance(dsn, str) or not dsn.startswith(("postgresql://","postgres://")):
            raise ValueError("explicit Postgres URL required")
        self._dsn = dsn
        self._lock = threading.Lock()
        self._ready = False
        self._last_cleanup = None

    def _connect(self):
        return psycopg.connect(self._dsn, connect_timeout=5)

    def initialize(self):
        with self._lock:
            if self._ready:
                return
            with self._connect() as db:
                db.execute("""CREATE TABLE IF NOT EXISTS ds_playtest_sessions (
                    session_id UUID PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    ended_at TIMESTAMPTZ,
                    outcome TEXT,
                    question_count INTEGER NOT NULL DEFAULT 0,
                    hint_count INTEGER NOT NULL DEFAULT 0,
                    rating SMALLINT CHECK (rating BETWEEN 1 AND 5),
                    issue TEXT,
                    feedback_note TEXT NOT NULL DEFAULT '',
                    transcript_disabled BOOLEAN NOT NULL DEFAULT FALSE
                )""")
                db.execute("""CREATE TABLE IF NOT EXISTS ds_playtest_consent (
                    session_id UUID PRIMARY KEY REFERENCES ds_playtest_sessions(session_id) ON DELETE CASCADE,
                    token_digest CHAR(64) NOT NULL UNIQUE,
                    consented_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""")
                db.execute("""CREATE TABLE IF NOT EXISTS ds_playtest_transcript (
                    session_id UUID NOT NULL REFERENCES ds_playtest_consent(session_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    kind TEXT NOT NULL,
                    player_text TEXT NOT NULL,
                    moderator_label TEXT NOT NULL,
                    moderator_text TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(session_id, ordinal)
                )""")
                # Safe additive migration for existing Render pilot records and
                # fresh Neon DBs. No user text is logged or exposed.
                db.execute("""ALTER TABLE ds_playtest_transcript
                    ADD COLUMN IF NOT EXISTS moderator_text TEXT NOT NULL DEFAULT ''""")
                db.execute("""ALTER TABLE ds_playtest_sessions
                    ADD COLUMN IF NOT EXISTS feedback_note TEXT NOT NULL DEFAULT ''""")
                db.execute("CREATE INDEX IF NOT EXISTS ds_playtest_case ON ds_playtest_sessions(case_id)")
                db.execute("CREATE INDEX IF NOT EXISTS ds_playtest_time ON ds_playtest_sessions(created_at)")
                db.execute("CREATE INDEX IF NOT EXISTS ds_playtest_transcript_time ON ds_playtest_transcript(recorded_at)")
            self._ready = True

    def _prune_if_due(self):
        # Bounded lazy purging on subsequent traffic; a daily scheduled
        # cleanup job is needed for a hard wall-clock deletion guarantee.
        now = datetime.now(timezone.utc)
        if self._last_cleanup and now - self._last_cleanup < timedelta(hours=1):
            return
        with self._lock:
            if self._last_cleanup and now - self._last_cleanup < timedelta(hours=1):
                return
            with self._connect() as db:
                db.execute("DELETE FROM ds_playtest_transcript WHERE recorded_at < now() - interval '30 days'")
                db.execute("DELETE FROM ds_playtest_sessions WHERE created_at < now() - interval '90 days'")
            self._last_cleanup = now

    def start(self, case_id, revision):
        if not CASE_ID.fullmatch(case_id):
            raise ValueError("experimental case IDs only")
        if not isinstance(revision, str) or len(revision)>64:
            raise ValueError("invalid revision")
        self.initialize()
        self._prune_if_due()
        sid = str(uuid4())
        with self._connect() as db:
            db.execute("INSERT INTO ds_playtest_sessions(session_id,case_id,revision) VALUES (%s,%s,%s)",
                       (sid,case_id,revision))
        return sid

    def consent(self, sid):
        """Return one-time deletion receipt, never record raw token in DB."""
        token = secrets.token_urlsafe(32)
        digest = sha256(token.encode()).hexdigest()
        self.initialize()
        with self._connect() as db:
            row=db.execute("SELECT transcript_disabled FROM ds_playtest_sessions WHERE session_id=%s FOR UPDATE",(sid,)).fetchone()
            if not row or row[0]:
                raise ValueError("session not eligible for transcript sharing")
            prior=db.execute("SELECT 1 FROM ds_playtest_consent WHERE session_id=%s",(sid,)).fetchone()
            if prior:
                raise ValueError("session has already opted in")
            db.execute("INSERT INTO ds_playtest_consent(session_id,token_digest) VALUES (%s,%s)",(sid,digest))
        return token

    def record(self, sid, ordinal, kind, text, label, *, consent_on=False, moderator_text=""):
        if kind not in KINDS or label not in LABELS:
            raise ValueError("unsupported playtest event")
        if not isinstance(ordinal, int) or not 1<=ordinal<=200:
            raise ValueError("event limit exceeded")
        safe=redact(text) if consent_on else ""
        safe_reply=redact(moderator_text) if consent_on else ""
        with self._connect() as db:
            # Store no text at all when opted out. Hint/reveal actions have
            # separate counts/outcomes; count only actual player questions.
            if kind in {"question", "private_guess"}:
                db.execute("""UPDATE ds_playtest_sessions
                    SET question_count=question_count+1 WHERE session_id=%s""",(sid,))
            if consent_on:
                db.execute("""INSERT INTO ds_playtest_transcript
                    (session_id, ordinal, kind, player_text, moderator_label, moderator_text)
                    SELECT %s,%s,%s,%s,%s,%s WHERE EXISTS (
                      SELECT 1 FROM ds_playtest_consent c
                      JOIN ds_playtest_sessions s ON s.session_id=c.session_id
                      WHERE c.session_id=%s AND NOT s.transcript_disabled
                    ) ON CONFLICT DO NOTHING""",
                    (sid,ordinal,kind,safe,label,safe_reply,sid))

    def hint(self, sid):
        with self._connect() as db:
            db.execute("UPDATE ds_playtest_sessions SET hint_count=hint_count+1 WHERE session_id=%s",(sid,))

    def finish(self,sid,outcome):
        if outcome not in {"solved","revealed"}:
            raise ValueError("invalid outcome")
        with self._connect() as db:
            db.execute("""UPDATE ds_playtest_sessions SET outcome=%s,ended_at=now()
                WHERE session_id=%s AND ended_at IS NULL""",(outcome,sid))

    def feedback(self,sid,rating,issue,note=""):
        if type(rating) is not int or not 1<=rating<=5 or issue not in SAFE_ISSUES:
            raise ValueError("invalid feedback")
        if not isinstance(note, str) or len(note)>500:
            raise ValueError("invalid feedback note")
        safe_note = redact(note)
        with self._connect() as db:
            row=db.execute("""UPDATE ds_playtest_sessions SET rating=%s,issue=%s,feedback_note=%s
                WHERE session_id=%s AND ended_at IS NOT NULL AND rating IS NULL
                RETURNING session_id""",(rating,issue,safe_note,sid)).fetchone()
            if row is None:
                return "duplicate"
        return "created"

    def disable_transcript(self,sid):
        """After a multiplayer join: stop all capture and purge earlier text."""
        with self._connect() as db:
            db.execute("DELETE FROM ds_playtest_consent WHERE session_id=%s",(sid,))
            db.execute("UPDATE ds_playtest_sessions SET transcript_disabled=TRUE WHERE session_id=%s",(sid,))

    def delete_receipt(self, token):
        if not isinstance(token,str) or not 20<=len(token)<=150:
            return False
        digest=sha256(token.encode()).hexdigest()
        with self._connect() as db:
            row=db.execute("""DELETE FROM ds_playtest_consent
                WHERE token_digest=%s RETURNING session_id""",(digest,)).fetchone()
            if row:
                db.execute("UPDATE ds_playtest_sessions SET transcript_disabled=TRUE WHERE session_id=%s",(row[0],))
        return bool(row)

    def summarize(self):
        """Aggregate-only admin-side access; never expose to public API."""
        self.initialize()
        with self._connect() as db:
            return db.execute("""SELECT case_id,count(*),count(rating),
                avg(rating),count(*) FILTER (WHERE outcome='solved')
                FROM ds_playtest_sessions GROUP BY case_id ORDER BY case_id""").fetchall()
