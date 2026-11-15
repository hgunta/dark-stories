"""Star-first post-game feedback and one optional follow-up.

Exercise the API with the process-local store so the tests are independent of
database credentials; real playtest storage has an equivalent guarded update.
"""
import pytest
from backend.feedback import FeedbackStore


@pytest.fixture(autouse=True)
def use_local_feedback(monkeypatch, isolated_app):
    monkeypatch.setattr(isolated_app, "_playtest_case_enabled", lambda _case: False)
    monkeypatch.setattr(isolated_app, "feedback_store", FeedbackStore())


def finish(client, room):
    resp=client.post("/api/reveal", json={"room_id":room["room_id"],"text":"/reveal"})
    assert resp.status_code==200


def test_rating_saved_without_questions_then_single_followup(client, create_room, isolated_app):
    room=create_room("ms-002")
    payload={"room_id":room["room_id"],"rating":4,"issue":"confusing_clues","note":"The yes/no answers were unclear"}
    assert client.post("/api/feedback/details",json=payload).status_code==409
    finish(client,room)
    assert client.post("/api/feedback/details",json=payload).status_code==409
    saved=client.post("/api/feedback",json={"room_id":room["room_id"],"rating":4})
    assert saved.status_code==201
    assert isolated_app.feedback_store._items[room["room_id"]]["rating"]==4
    assert isolated_app.feedback_store._items[room["room_id"]]["note"]==""
    follow=client.post("/api/feedback/details",json=payload)
    assert follow.status_code==200
    assert follow.json()=={"status":"received"}
    assert isolated_app.feedback_store._items[room["room_id"]]["issue"]=="confusing_clues"
    assert isolated_app.feedback_store._items[room["room_id"]]["note"]==payload["note"]
    assert client.post("/api/feedback/details",json=payload).status_code==409
    assert client.post("/api/feedback",json={"room_id":room["room_id"],"rating":5}).status_code==409


def test_followup_rejects_changed_rating_and_invalid_text(client, create_room):
    room=create_room("ms-001")
    finish(client,room)
    client.post("/api/feedback",json={"room_id":room["room_id"],"rating":5})
    for req in (
        {"room_id":room["room_id"],"rating":3,"issue":"other","note":"Wait"},
        {"room_id":room["room_id"],"rating":5,"issue":"none","note":""},
    ):
        assert client.post("/api/feedback/details",json=req).status_code in (409,422)
    invalid={"room_id":room["room_id"],"rating":5,"issue":"other","note":"x"*501}
    assert client.post("/api/feedback/details",json=invalid).status_code==422
    assert client.get("/api/feedback/details").status_code==405
    assert client.get("/api/feedback").status_code==405
