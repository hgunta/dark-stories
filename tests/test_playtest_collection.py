"""Experiment-only opt-in collection, redaction, deletion, durable feedback wiring.

All API tests run with an in-memory spy, never an actual database or network.
Postgres integration requires an explicit database connection for live smoke.
"""
import pytest

class FakePlaytestStore:
    def __init__(self):
        self.sessions={}
        self.events=[]
        self.consents=set()
        self.deleted=[]
    def start(self,case_id,revision):
        sid="anonymous-"+str(len(self.sessions)+1)
        self.sessions[sid]={"case":case_id,"revision":revision,"rating":None,"ended":False}
        return sid
    def consent(self,sid):
        if sid in self.consents:raise ValueError("already")
        self.consents.add(sid)
        return "test-delete-receipt-token-123456789"
    def record(self,sid,ordinal,kind,text,label,*,consent_on):
        self.events.append((sid,ordinal,kind,text if consent_on and sid in self.consents else "",label,consent_on))
    def hint(self,sid):
        self.sessions[sid]["hints"]=self.sessions[sid].get("hints",0)+1
    def finish(self,sid,outcome):
        self.sessions[sid]["ended"]=True
        self.sessions[sid]["outcome"]=outcome
    def feedback(self,sid,rating,issue):
        session=self.sessions[sid]
        if session["rating"] is not None:return "duplicate"
        session["rating"]=rating
        session["issue"]=issue
        return "created"
    def delete_receipt(self,token):
        self.deleted.append(token)
        self.consents.clear()
        return True
    def disable_transcript(self,sid):
        self.consents.discard(sid)
        self.sessions[sid]["multiplayer"]=True

@pytest.fixture
def store(monkeypatch,isolated_app):
    fake=FakePlaytestStore()
    monkeypatch.setattr(isolated_app,"playtest_store",fake)
    return fake

def test_no_text_saved_without_opt_in(client,create_room,store):
    room=create_room("ex-001")
    a=client.post("/api/message",json={"room_id":room["room_id"],"text":"Is that resident counted twice?"})
    assert a.status_code==200
    assert store.events[0][3]==""
    assert store.events[0][5] is False
    assert store.sessions["anonymous-1"]["case"]=="ex-001"

def test_opt_in_only_affects_future_messages(client,create_room,store):
    room=create_room("ex-001")
    client.post("/api/message",json={"room_id":room["room_id"],"text":"first question"})
    granted=client.post("/api/playtest/consent",json={"room_id":room["room_id"],"consent_key":room["playtest_consent_key"]})
    assert granted.status_code==200
    assert granted.json()["enabled"] is True
    assert len(granted.json()["deletion_token"])>=20
    client.post("/api/message",json={"room_id":room["room_id"],"text":"second question"})
    assert store.events[0][3]==""
    assert store.events[1][3]=="second question"
    again=client.post("/api/playtest/consent",json={"room_id":room["room_id"],"consent_key":room["playtest_consent_key"]})
    assert again.status_code==409

def test_deletion_receipt_and_opt_in_stop(client,create_room,store):
    room=create_room("ex-001")
    receipt=client.post("/api/playtest/consent",json={"room_id":room["room_id"],"consent_key":room["playtest_consent_key"]}).json()["deletion_token"]
    deleted=client.post("/api/playtest/delete",json={"deletion_token":receipt})
    assert deleted.status_code==200
    assert deleted.json()=={"deleted":True}
    assert store.deleted==[receipt]
    client.post("/api/message",json={"room_id":room["room_id"],"text":"after deletion"})
    assert store.events[-1][3]==""

def test_join_revokes_transcript_sharing(client,create_room,store):
    room=create_room("ex-001")
    grant=client.post("/api/playtest/consent",json={"room_id":room["room_id"],"consent_key":room["playtest_consent_key"]})
    assert grant.status_code==200
    join=client.get("/api/join/"+room["room_code"])
    assert join.status_code==200
    assert store.sessions["anonymous-1"]["multiplayer"] is True
    assert store.consents==set()
    assert client.post("/api/playtest/consent",json={"room_id":room["room_id"],"consent_key":room["playtest_consent_key"]}).status_code==409

def test_structured_feedback_is_durable_only_when_store_active(client,create_room,store):
    room=create_room("ex-002")
    client.post("/api/hint",json={"room_id":room["room_id"],"text":"/hint"})
    assert store.sessions["anonymous-1"]["hints"]==1
    client.post("/api/reveal",json={"room_id":room["room_id"],"text":"/reveal"})
    r=client.post("/api/feedback",json={"room_id":room["room_id"],"rating":2,"issue":"incorrect_answer"})
    assert r.status_code==201
    assert store.sessions["anonymous-1"]["rating"]==2
    assert store.sessions["anonymous-1"]["issue"]=="incorrect_answer"
    assert store.sessions["anonymous-1"]["outcome"]=="revealed"
    assert client.post("/api/feedback",json={"room_id":room["room_id"],"rating":2}).status_code==409

def test_no_enabled_store_fails_closed_for_experiment(client,create_room):
    room=create_room("ex-001")
    assert client.post("/api/playtest/consent",json={"room_id":room["room_id"],"consent_key":room["playtest_consent_key"]}).status_code==503
    client.post("/api/reveal",json={"room_id":room["room_id"],"text":"/reveal"})
    assert client.post("/api/feedback",json={"room_id":room["room_id"],"rating":5}).status_code==503

def test_other_main_cases_still_use_existing_feedback(client,create_room,store):
    room=create_room("ms-001")
    client.post("/api/reveal",json={"room_id":room["room_id"],"text":"/reveal"})
    assert client.post("/api/feedback",json={"room_id":room["room_id"],"rating":4}).status_code==201
    assert not store.sessions

def test_text_redaction_is_bounded():
    from playtest_store import redact
    text="Email alice@example.com or call (415) 555-1234 and open https://example.com/a."
    cleaned=redact(text)
    assert "alice@" not in cleaned
    assert "415" not in cleaned
    assert "https:" not in cleaned
    assert "[EMAIL]" in cleaned and "[PHONE]" in cleaned and "[URL]" in cleaned
    assert len(redact("x"*2000))==1000

def test_ui_opt_in_unchecked_and_delete_available():
    from pathlib import Path
    html=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    assert 'type="checkbox" id="playtest-opt-in"' in html
    assert 'id="delete-playtest-token"' in html
    assert "DARK_STORIES_PLAYTEST_DB_URL" not in html
    assert "/api/playtest/consent" in html
    assert "/api/playtest/delete" in html

def test_only_creator_can_opt_in(client,create_room,store):
    room=create_room("ex-001")
    forged=client.post("/api/playtest/consent",json={
        "room_id":room["room_id"],"consent_key":"x"*43})
    assert forged.status_code==403
    assert store.consents==set()
    valid=client.post("/api/playtest/consent",json={
        "room_id":room["room_id"],"consent_key":room["playtest_consent_key"]})
    assert valid.status_code==200

def test_main_case_never_exposes_consent_key(client,create_room,store):
    room=create_room("ms-001")
    assert "playtest_consent_key" not in room
