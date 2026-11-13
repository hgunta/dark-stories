"""Disposable PostgreSQL integration: consent, review, export, deletion cascade."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from playtest_store import PlaytestStore
from playtest_review import ReviewStore

def main():
 dsn=os.environ.get("TEST_PLAYTEST_DB_DSN")
 if not dsn:raise SystemExit("Test-only DSN required")
 db=PlaytestStore(dsn)
 shared=db.start("ex-001","synthetic-review-test")
 unshared=db.start("ex-002","synthetic-review-test")
 review=ReviewStore(db)
 try:
  db.record(unshared,1,"question","NOT_CONSENTED","no",
            consent_on=False,moderator_text="Not saved")
  db.finish(unshared,"revealed")
  db.feedback(unshared,2,"incorrect_answer")
  assert review.sessions()==[]
  token=db.consent(shared)
  db.record(shared,1,"question","A person was counted twice","almost_solved",
            consent_on=True,moderator_text="You're close. Put pieces together.")
  db.record(shared,2,"hint","","hint",consent_on=True,
            moderator_text="Hint 1: Look at the names")
  db.finish(shared,"solved")
  db.feedback(shared,1,"incorrect_answer")
  summary=review.summary()
  assert summary["sessions"]==2 and summary["rated"]==2
  assert summary["shared_sessions"]==1
  sessions=review.sessions()
  assert len(sessions)==1 and sessions[0]["turn_count"]==2
  transcript=review.transcript(shared)
  assert [t["kind"] for t in transcript["turns"]]==["question","hint"]
  assert review.annotate(shared,1,"Solved","false_negative")
  assert len(review.reviewed_examples())==1
  example=review.reviewed_examples()[0]
  assert example["human_gold_label"]=="Solved"
  assert example["approved_for_training"] is False
  assert not any("session_id" in e for e in review.reviewed_examples())
  try:review.annotate(shared,2,"Solved","false_negative")
  except ValueError:pass
  else:raise AssertionError("Hint must be unreviewable")
  assert db.delete_receipt(token)
  assert review.transcript(shared) is None
  assert review.sessions()==[]
  assert review.reviewed_examples()==[]
  with db._connect() as conn:
   n=conn.execute("SELECT count(*) FROM ds_playtest_review_labels WHERE session_id=%s",(shared,)).fetchone()[0]
   assert n==0
  print("PASS: Postgres consent-filtered reviewer sessions, labels, export, and deletion cascade")
 finally:
  with db._connect() as conn:
   conn.execute("DELETE FROM ds_playtest_sessions WHERE session_id IN (%s,%s)",(shared,unshared))

if __name__=="__main__":
 main()
