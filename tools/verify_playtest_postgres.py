"""CI-only smoke of real PostgreSQL persistence, consent and deletion.

Requires TEST_PLAYTEST_DB_DSN against disposable test DB. Never use a
production URL; no real player text is used. No credentials are printed.
"""
import os
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from playtest_store import PlaytestStore

def main():
    dsn=os.environ.get("TEST_PLAYTEST_DB_DSN")
    if not dsn:
        raise SystemExit("TEST_PLAYTEST_DB_DSN required")
    store=PlaytestStore(dsn)
    sid=store.start("ex-001","test-revision")
    try:
        # Only counts before consent, no chat text.
        store.record(sid,1,"question","FIRST_SECRET_TEXT","yes",consent_on=False)
        with store._connect() as db:
            assert db.execute("SELECT question_count FROM ds_playtest_sessions WHERE session_id=%s",(sid,)).fetchone()[0]==1
            assert db.execute("SELECT count(*) FROM ds_playtest_transcript WHERE session_id=%s",(sid,)).fetchone()[0]==0
        token=store.consent(sid)
        with store._connect() as db:
            digest=db.execute("SELECT token_digest FROM ds_playtest_consent WHERE session_id=%s",(sid,)).fetchone()[0]
            assert digest==sha256(token.encode()).hexdigest()
            assert token not in digest
        store.record(sid,2,"question","alice@example.com called (415) 555-1234","yes",consent_on=True)
        with store._connect() as db:
            row=db.execute("SELECT player_text,moderator_label FROM ds_playtest_transcript WHERE session_id=%s",(sid,)).fetchone()
            assert "alice@example" not in row[0]
            assert "415" not in row[0]
            assert "[EMAIL]" in row[0] and "[PHONE]" in row[0] and row[1]=="yes"
        store.hint(sid)
        store.finish(sid,"solved")
        assert store.feedback(sid,4,"none")=="created"
        assert store.feedback(sid,2,"other")=="duplicate"
        assert store.delete_receipt(token) is True
        with store._connect() as db:
            assert db.execute("SELECT count(*) FROM ds_playtest_transcript WHERE session_id=%s",(sid,)).fetchone()[0]==0
            assert db.execute("SELECT count(*) FROM ds_playtest_consent WHERE session_id=%s",(sid,)).fetchone()[0]==0
            assert db.execute("SELECT rating,hint_count FROM ds_playtest_sessions WHERE session_id=%s",(sid,)).fetchone()==(4,1)
        # Even if a stale application flag still thinks the player consented,
        # the DB refuses to write anything after token revocation.
        store.record(sid,3,"question","SHOULD_NOT_STORE","yes",consent_on=True)
        with store._connect() as db:
            assert db.execute("SELECT count(*) FROM ds_playtest_transcript WHERE session_id=%s",(sid,)).fetchone()[0]==0
        print("Postgres consent, redaction, rating, revocation and no-consent smoke passed")
    finally:
        with store._connect() as db:
            db.execute("DELETE FROM ds_playtest_sessions WHERE session_id=%s",(sid,))
if __name__=="__main__":
    main()
