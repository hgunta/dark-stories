#!/usr/bin/env python3
"""One-time public preview integration smoke. Never prints opt-in receipts/text."""
import json
import time
import urllib.error
import urllib.request

ROOT="https://dark-stories-preview.onrender.com"

def req(path, payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    request=urllib.request.Request(ROOT+path,data=data,headers=(
        {"Content-Type":"application/json"} if data is not None else {}))
    with urllib.request.urlopen(request,timeout=50) as response:
        return json.load(response)

def main():
    for attempt in range(40):
        try:
            status=req("/api/neon/status")
            if "postgres_connected" in status:
                break
        except Exception:
            pass
        time.sleep(5)
    else:
        raise RuntimeError("Preview hasn't deployed Neon integration status yet")
    print("postgres_connected:",status["postgres_connected"])
    print("gateway_credential_configured:",status["ai_gateway_configured"])
    print("gateway_active_for_moderator:",status["ai_gateway_active_for_moderator"])
    print("realtime_configured:",status["realtime_configured"])
    print("realtime_live_subscription_verified:",status["realtime_live_subscription_verified"])
    if not status["postgres_connected"]:
        raise RuntimeError("Postgres preview connection failed")
    catalog=req("/api/neon/gateway_catalog")
    print("gateway_catalog_reachable:",catalog.get("reachable",False))
    print("gateway_enabled_models:",catalog.get("available_model_count",0))
    if not status["ai_gateway_configured"] or not status["realtime_configured"]:
        raise RuntimeError("Missing gateway/realtime environment wiring")

    # Real hosted DB interaction via the app: non-consented session + opted-in
    # session with hint/reveal and deletion receipt. No raw data is printed.
    normal=req("/api/create_room",{"mystery_id":"ex-001"})
    req("/api/hint",{"room_id":normal["room_id"],"text":"/hint"})
    req("/api/reveal",{"room_id":normal["room_id"],"text":"/reveal"})
    print("unconsented_experimental_gameplay:passed")
    room=req("/api/create_room",{"mystery_id":"ex-002"})
    ticket=req("/api/playtest/consent",{
        "room_id":room["room_id"],"consent_key":room["playtest_consent_key"]})
    if not ticket.get("enabled"):
        raise RuntimeError("Cannot enable opt-in consent")
    hint=req("/api/hint",{"room_id":room["room_id"],"text":"/hint"})
    reveal=req("/api/reveal",{"room_id":room["room_id"],"text":"/reveal"})
    if not hint["reply"].startswith("Hint") or not reveal["solved"]:
        raise RuntimeError("Game failed with opt-in collection")
    rating=req("/api/feedback",{"room_id":room["room_id"],"rating":4,"issue":"none"})
    if rating.get("status")!="received":
        raise RuntimeError("Rating not persisted")
    deletion=req("/api/playtest/delete",{"deletion_token":ticket["deletion_token"]})
    if not deletion.get("deleted"):
        raise RuntimeError("Transcript delete failed")
    print("consent_hint_reveal_rating_delete:passed")
    print("No secrets, deletion token, or player text written to workflow logs")

if __name__=="__main__":
    main()
