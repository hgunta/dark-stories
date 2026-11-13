"""Private dashboard security and consent tests, no external AI or DB."""
from types import SimpleNamespace
from uuid import uuid4
import pytest

class FakeReviewStore:
    def __init__(self, db):
        self.db=db
    def summary(self):
        return {"sessions":2,"solved":1,"rated":1,"average_rating":2.0,
                "solved_rate":.5,"shared_sessions":1,"reviewed_turns":self.db.reviews}
    def sessions(self):
        return [{"id":self.db.sid,"case_id":"ex-001","revision":"preview",
                 "started_at":"2026-11-12T12:00:00+00:00","finished_at":None,
                 "outcome":None,"question_count":2,"hint_count":0,"rating":2,
                 "issue":"incorrect_answer","turn_count":2,
                 "reviewed_turns":self.db.reviews}]
    def transcript(self,sid):
        if sid!=self.db.sid or not self.db.consented:return None
        return {"session_id":sid,"case_id":"ex-001","revision":"preview",
                "outcome":None,"rating":2,"issue":"incorrect_answer",
                "turns":[{"ordinal":1,"kind":"question",
                   "recorded_at":"2026-11-12T12:00:00+00:00",
                   "player_text":"A survivor was counted twice",
                   "moderator_label":"AlmostSolved",
                   "moderator_text":"You're close.",
                   "correct_label":self.db.correct_label,
                   "reason_code":self.db.reason_code},
                 {"ordinal":2,"kind":"hint",
                  "recorded_at":"2026-11-12T12:01:00+00:00","player_text":"",
                  "moderator_label":"hint","moderator_text":"Hint: consider the list",
                  "correct_label":None,"reason_code":None}]}
    def annotate(self,sid,ordinal,label,reason):
        if sid!=self.db.sid or not self.db.consented:return False
        if ordinal!=1:raise ValueError("can't annotate hint")
        self.db.correct_label=label
        self.db.reason_code=reason
        self.db.reviews=1
        return True
    def reviewed_examples(self):
        if not self.db.consented or not self.db.reviews:return []
        return [{"case_id":"ex-001","case_revision":"preview",
                 "ordinal":1,"kind":"question",
                 "player_text_redacted":"A survivor was counted twice",
                 "moderator_label":"AlmostSolved",
                 "moderator_response_redacted":"You're close.",
                 "human_gold_label":self.db.correct_label,
                 "issue_reason":self.db.reason_code,
                 "approved_for_training":False}]

@pytest.fixture
def private_review(monkeypatch, isolated_app, client):
    import playtest_review_routes as routes
    db=SimpleNamespace(sid=str(uuid4()),reviews=0,consented=True,
                       correct_label=None,reason_code=None)
    monkeypatch.setenv("DARK_STORIES_REVIEW_USER","reviewer")
    monkeypatch.setenv("DARK_STORIES_REVIEW_PASSWORD","s"*44)
    monkeypatch.setattr(routes,"ReviewStore",lambda store:FakeReviewStore(db))
    isolated_app.app.state.playtest_store_for_review=object()
    auth={"Authorization":"Basic "+__import__("base64").b64encode(
         b"reviewer:"+b"s"*44).decode()}
    yield client,db,auth
    isolated_app.app.state.playtest_store_for_review=None

def test_review_disabled_without_secret(client,monkeypatch):
    monkeypatch.delenv("DARK_STORIES_REVIEW_PASSWORD",raising=False)
    assert client.get("/review/").status_code==404
    assert client.get("/api/review/overview").status_code==404
    assert client.get("/api/review/export.jsonl").status_code==404

def test_untrusted_clients_cannot_read_conversations(private_review):
    client,db,auth=private_review
    for url in ["/review/","/review/app.js","/api/review/overview",
                "/api/review/session/"+db.sid,"/api/review/export.jsonl"]:
        assert client.get(url).status_code==401
        assert client.get(url,headers={"Authorization":"Basic YmFkOmJhZA=="}).status_code==401

def test_authenticated_dashboard_and_consent_filter(private_review):
    client,db,auth=private_review
    html=client.get("/review/",headers=auth)
    assert html.status_code==200
    assert "Private Playtest Review" in html.text
    assert html.headers["cache-control"].startswith("no-store")
    assert "frame-ancestors 'none'" in html.headers["content-security-policy"]
    overview=client.get("/api/review/overview",headers=auth)
    assert overview.status_code==200
    assert overview.json()["summary"]["solved_rate"]==.5
    transcript=client.get("/api/review/session/"+db.sid,headers=auth)
    assert transcript.json()["turns"][0]["moderator_text"]=="You're close."
    db.consented=False
    assert client.get("/api/review/session/"+db.sid,headers=auth).status_code==404

def test_write_requires_same_origin_and_explicit_intent(private_review):
    client,db,auth=private_review
    data={"session_id":db.sid,"ordinal":1,"correct_label":"Solved","reason_code":"false_negative"}
    def send(headers):
        return client.post("/api/review/label",json=data,headers={**auth,**headers})
    assert send({}).status_code==403
    assert send({"Origin":"https://evil.example","X-Review-Intent":"annotate"}).status_code==403
    assert send({"Origin":"https://dark-stories-preview.onrender.com"}).status_code==403
    good={"Origin":"https://dark-stories-preview.onrender.com","X-Review-Intent":"annotate"}
    assert send(good).json()=={"saved":True}
    assert db.correct_label=="Solved" and db.reason_code=="false_negative"
    assert client.get("/api/review/export.jsonl",headers=auth).json if False else True
    export=client.get("/api/review/export.jsonl",headers=auth)
    assert export.status_code==200
    assert export.headers["content-type"].startswith("application/x-ndjson")
    assert export.headers["cache-control"].startswith("no-store")
    example=__import__("json").loads(export.text)
    assert example["human_gold_label"]=="Solved"
    assert example["approved_for_training"] is False
    assert "session_id" not in example
    db.consented=False
    assert client.get("/api/review/export.jsonl",headers=auth).text==""

def test_invalid_review_and_hint_rejected(private_review):
    client,db,auth=private_review
    heads={**auth,"Origin":"https://dark-stories-preview.onrender.com",
           "X-Review-Intent":"annotate"}
    base={"session_id":db.sid,"ordinal":1,"correct_label":"Solved",
          "reason_code":"false_negative"}
    bad=dict(base,correct_label="InventedResponse")
    assert client.post("/api/review/label",json=bad,headers=heads).status_code==422
    hint=dict(base,ordinal=2)
    assert client.post("/api/review/label",json=hint,headers=heads).status_code==422
    assert client.get("/api/review/session/not-a-uuid",headers=auth).status_code in (404,422)

def test_review_page_has_no_secret_or_inline_scripts():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/"backend/review_dashboard/index.html").read_text()
    assert "<script defer src=" in html
    assert "<script>" not in html
    assert "innerHTML" not in (root/"backend/review_dashboard/app.js").read_text()
    assert "DARK_STORIES_REVIEW_PASSWORD" not in html
