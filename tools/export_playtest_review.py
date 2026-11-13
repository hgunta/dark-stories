#!/usr/bin/env python3
"""Export explicitly consented playtest turns for HUMAN REVIEW, not model training.

Needs DARK_STORIES_PLAYTEST_DB_URL in the local owner's environment; never
accepts a public HTTP endpoint. Writes a new 0600 file only, never prints
player text, secrets or deletion receipts. No direct training JSONL output.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from playtest_store import PlaytestStore,redact

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--limit",type=int,default=500)
    a=p.parse_args(argv)
    if not 1<=a.limit<=2000:
        p.error("limit must be from 1 to 2000")
    dsn=os.getenv("DARK_STORIES_PLAYTEST_DB_URL")
    if not dsn:
        p.error("DARK_STORIES_PLAYTEST_DB_URL must be configured outside the source tree")
    store=PlaytestStore(dsn)
    store.initialize()
    with store._connect() as db:
        rows=db.execute("""SELECT s.case_id,s.revision,t.kind,t.player_text,
                    t.moderator_label,t.moderator_text,t.recorded_at
                FROM ds_playtest_transcript t
                JOIN ds_playtest_consent c ON c.session_id=t.session_id
                JOIN ds_playtest_sessions s ON s.session_id=t.session_id
                WHERE NOT s.transcript_disabled
                  AND t.recorded_at >= now() - interval '30 days'
                ORDER BY t.recorded_at,t.ordinal
                LIMIT %s""",(a.limit,)).fetchall()
    # Output is intentionally NOT suitable for automated training: reviewers
    # must spot residual PII and annotate correctness before use.
    path=a.output.expanduser().resolve()
    fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as out:
        for case_id,revision,kind,player_text,label,moderator_text,at in rows:
            out.write(json.dumps({
                "case_id":case_id,"revision":revision,"kind":kind,
                "question_redacted":redact(player_text),"moderator_label":label,
                "moderator_reply_redacted":redact(moderator_text),
                "recorded_date":at.date().isoformat(),
                "human_gold_label":None,"issue_reason":None,
                "approved_for_training":False
            },ensure_ascii=False)+"\n")
    print(f"Created restricted-permissions reviewer export with {len(rows)} rows.")
    print("Not approved for training. Check for residual personal information and review each label.")
if __name__=="__main__":
    raise SystemExit(main())
