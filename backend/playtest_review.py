"""Private reviewer data access: consent-gated and bounded.

No public route is defined here. All reads must be called through the
authenticated review router; never expose this adapter through normal gameplay.
"""
from uuid import UUID
from datetime import datetime, timezone

REVIEW_LABELS = frozenset({"Yes", "No", "Irrelevant", "Unknown", "AskYesNo",
                           "AlmostSolved", "Solved"})
REASON_CODES = frozenset({"correct", "false_negative", "false_positive",
    "incorrect_yes_no", "unfair_solution", "spoiler", "unclear_story", "other"})

def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as e:
        raise ValueError("invalid session identifier") from e

class ReviewStore:
    def __init__(self, playtest_store):
        self.store = playtest_store

    def initialize(self):
        self.store.initialize()
        with self.store._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ds_playtest_review_labels (
              session_id UUID NOT NULL,
              ordinal INTEGER NOT NULL,
              correct_label TEXT NOT NULL,
              reason_code TEXT NOT NULL,
              reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY(session_id,ordinal),
              FOREIGN KEY(session_id,ordinal)
                REFERENCES ds_playtest_transcript(session_id,ordinal)
                ON DELETE CASCADE
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS ds_playtest_review_time
                ON ds_playtest_review_labels(reviewed_at)""")

    def summary(self):
        self.initialize()
        with self.store._connect() as db:
            row=db.execute("""SELECT count(*),
                  count(*) FILTER (WHERE outcome='solved'),
                  count(*) FILTER (WHERE rating IS NOT NULL),
                  round(avg(rating)::numeric,2)
                FROM ds_playtest_sessions""").fetchone()
            shared=db.execute("""SELECT count(DISTINCT s.session_id)
                FROM ds_playtest_sessions s
                JOIN ds_playtest_consent c USING(session_id)
                WHERE NOT s.transcript_disabled
                  AND EXISTS (SELECT 1 FROM ds_playtest_transcript t
                              WHERE t.session_id=s.session_id)""").fetchone()[0]
            flagged=db.execute("""SELECT count(*) FROM ds_playtest_review_labels""").fetchone()[0]
        total,solved,rated,average=row
        return {"sessions":total,"solved":solved,"rated":rated,
                "average_rating":float(average) if average is not None else None,
                "solved_rate":round(solved/total,3) if total else None,
                "shared_sessions":shared,"reviewed_turns":flagged}

    def feedback_notes(self, limit=40):
        """Owner-only comments, independent of transcript consent."""
        self.initialize()
        limit=max(1,min(int(limit),50))
        with self.store._connect() as db:
            rows=db.execute("""SELECT case_id,rating,issue,feedback_note,ended_at
                FROM ds_playtest_sessions WHERE feedback_note <> '' AND rating IS NOT NULL
                ORDER BY ended_at DESC LIMIT %s""",(limit,)).fetchall()
        return [{"case_id":r[0],"rating":r[1],"issue":r[2],
                 "note":r[3],"submitted_at":r[4].isoformat() if r[4] else None} for r in rows]

    def sessions(self, limit=40):
        self.initialize()
        limit=max(1,min(int(limit),50))
        with self.store._connect() as db:
            rows=db.execute("""SELECT s.session_id::text,s.case_id,s.revision,
                    s.created_at,s.ended_at,s.outcome,s.question_count,
                    s.hint_count,s.rating,s.issue,
                    (SELECT count(*) FROM ds_playtest_transcript t WHERE t.session_id=s.session_id),
                    (SELECT count(*) FROM ds_playtest_review_labels r WHERE r.session_id=s.session_id)
                FROM ds_playtest_sessions s
                JOIN ds_playtest_consent c USING(session_id)
                WHERE NOT s.transcript_disabled
                  AND EXISTS (SELECT 1 FROM ds_playtest_transcript t
                              WHERE t.session_id=s.session_id)
                ORDER BY s.created_at DESC
                LIMIT %s""",(limit,)).fetchall()
        return [{"id":r[0],"case_id":r[1],"revision":r[2],
                 "started_at":r[3].isoformat(),"finished_at":r[4].isoformat() if r[4] else None,
                 "outcome":r[5],"question_count":r[6],"hint_count":r[7],
                 "rating":r[8],"issue":r[9],"turn_count":r[10],
                 "reviewed_turns":r[11]} for r in rows]

    def transcript(self, session_id):
        sid=_uuid(session_id)
        self.initialize()
        with self.store._connect() as db:
            session=db.execute("""SELECT s.case_id,s.revision,s.outcome,s.rating,s.issue
                FROM ds_playtest_sessions s
                JOIN ds_playtest_consent c USING(session_id)
                WHERE s.session_id=%s AND NOT s.transcript_disabled""",(sid,)).fetchone()
            if not session:
                return None
            rows=db.execute("""SELECT t.ordinal,t.kind,t.recorded_at,t.player_text,
                    t.moderator_label,t.moderator_text,
                    r.correct_label,r.reason_code
                FROM ds_playtest_transcript t
                LEFT JOIN ds_playtest_review_labels r
                   ON t.session_id=r.session_id AND t.ordinal=r.ordinal
                WHERE t.session_id=%s ORDER BY t.ordinal LIMIT 200""",(sid,)).fetchall()
        return {"session_id":sid,"case_id":session[0],"revision":session[1],
                "outcome":session[2],"rating":session[3],"issue":session[4],
                "turns":[{"ordinal":x[0],"kind":x[1],"recorded_at":x[2].isoformat(),
                          "player_text":x[3],"moderator_label":x[4],
                          "moderator_text":x[5],"correct_label":x[6],
                          "reason_code":x[7]} for x in rows]}

    def annotate(self,session_id,ordinal,correct_label,reason_code):
        sid=_uuid(session_id)
        if type(ordinal) is not int or not 1<=ordinal<=200:
            raise ValueError("invalid ordinal")
        if correct_label not in REVIEW_LABELS or reason_code not in REASON_CODES:
            raise ValueError("invalid reviewer label")
        self.initialize()
        with self.store._connect() as db:
            row=db.execute("""SELECT t.kind FROM ds_playtest_transcript t
                JOIN ds_playtest_consent c USING(session_id)
                JOIN ds_playtest_sessions s USING(session_id)
                WHERE t.session_id=%s AND t.ordinal=%s
                  AND NOT s.transcript_disabled FOR UPDATE OF t""",(sid,ordinal)).fetchone()
            if not row:
                return False
            if row[0] not in {"question","private_guess"}:
                raise ValueError("only player questions and theories are labelable")
            db.execute("""INSERT INTO ds_playtest_review_labels
                (session_id,ordinal,correct_label,reason_code)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (session_id,ordinal) DO UPDATE SET
                    correct_label=excluded.correct_label,
                    reason_code=excluded.reason_code,reviewed_at=now()""",
                (sid,ordinal,correct_label,reason_code))
        return True

    def reviewed_examples(self, limit=500):
        self.initialize()
        limit=max(1,min(int(limit),1000))
        with self.store._connect() as db:
            rows=db.execute("""SELECT s.case_id,s.revision,t.ordinal,t.kind,
                    t.player_text,t.moderator_label,t.moderator_text,
                    r.correct_label,r.reason_code
                FROM ds_playtest_review_labels r
                JOIN ds_playtest_transcript t
                  ON t.session_id=r.session_id AND t.ordinal=r.ordinal
                JOIN ds_playtest_consent c ON c.session_id=t.session_id
                JOIN ds_playtest_sessions s ON s.session_id=t.session_id
                WHERE NOT s.transcript_disabled
                ORDER BY r.reviewed_at DESC LIMIT %s""",(limit,)).fetchall()
        # Session and consent IDs are deliberately excluded from exports.
        return [{"case_id":r[0],"case_revision":r[1],"ordinal":r[2],
                 "kind":r[3],"player_text_redacted":r[4],
                 "moderator_label":r[5],"moderator_response_redacted":r[6],
                 "human_gold_label":r[7],"issue_reason":r[8],
                 "approved_for_training":False} for r in rows]
