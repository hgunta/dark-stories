"""One-time synthetic production beta smoke. No LLM calls, raw chat or secrets."""
import json
import urllib.request
import urllib.error

ROOT="https://dark-stories-8frx.onrender.com"

def get(path):
    with urllib.request.urlopen(ROOT+path,timeout=45) as r:
        return r.status,r.read().decode("utf-8")

def post(path,data):
    b=json.dumps(data).encode()
    req=urllib.request.Request(ROOT+path,data=b,headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=45) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read().decode())

def main():
    _,page=get("/")
    assert "Public beta" in page
    assert "function showFeedbackInChat()" in page
    assert "<details class=\"playtest-privacy-details\">" in page
    assert "checked id=\"playtest-opt-in\"" not in page
    assert "How was this case?" in page
    print("PUBLIC BETA FRONTEND: five-case UI, compact opt-in, in-chat feedback code verified")
    _,txt=get("/api/mysteries")
    normal=json.loads(txt)
    _,txt=get("/api/experimental_mysteries")
    experiments=json.loads(txt)
    assert {m["id"] for m in normal}=={"ms-001","ms-002","ms-003"}
    assert {m["id"] for m in experiments}=={"ex-001","ex-002"}
    denied=post("/api/create_room",{"mystery_id":"ms-004"})
    assert denied[0]==404
    print("CATALOG: 3 original + 2 experimental, hidden drafts reject direct starts")
    _,txt=get("/api/playtest/status")
    storage=json.loads(txt)
    assert storage["enabled"] is True and storage["all_cases"] is True,storage
    print("NEON: ready for anonymous metrics and voluntary text consent on all five cases")
    try:get("/review/")
    except urllib.error.HTTPError as e:assert e.code==404
    else:raise AssertionError("Private dashboard must not be enabled on production")
    print("REVIEW: private reviewer portal disabled on production")
    code,room=post("/api/create_room",{"mystery_id":"ms-001"})
    assert code==200 and room.get("playtest_consent_key")
    code,consent=post("/api/playtest/consent",{
        "room_id":room["room_id"],"consent_key":room["playtest_consent_key"]})
    assert code==200 and consent["enabled"] is True
    token=consent["deletion_token"]
    code,hint=post("/api/hint",{"room_id":room["room_id"],"text":"/hint"})
    assert code==200 and hint["reply"].startswith("Hint")
    code,reveal=post("/api/reveal",{"room_id":room["room_id"],"text":"/reveal"})
    assert code==200 and reveal["solved"]
    code,feedback=post("/api/feedback",{
        "room_id":room["room_id"],"rating":4,"issue":"none"})
    assert code==201 and feedback["status"]=="received"
    code,deleted=post("/api/playtest/delete",{"deletion_token":token})
    assert code==200 and deleted["deleted"]
    print("ORIGINAL CASE: consent, hint, reveal, durable rating, transcript deletion passed")
    code,experimental=post("/api/create_room",{"mystery_id":"ex-001"})
    assert code==200
    code,reveal2=post("/api/reveal",{"room_id":experimental["room_id"],"text":"/reveal"})
    assert code==200 and reveal2["solved"]
    code,rated=post("/api/feedback",{
        "room_id":experimental["room_id"],"rating":3,"issue":"confusing_clues"})
    assert code==201 and rated["status"]=="received"
    print("EXPERIMENTAL CASE: anonymous rating without transcript opt-in passed")
    print("Live production smoke passed. No paid moderator calls, credentials or receipts logged.")

if __name__=="__main__":main()
