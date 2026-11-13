"""Post-game feedback MVP: structured ratings, one per finished room, no raw text."""
import pytest

from backend.feedback import FeedbackStore


@pytest.fixture(autouse=True)
def isolated_feedback(isolated_app, monkeypatch):
    monkeypatch.setattr(isolated_app, "feedback_store", FeedbackStore())


def submit(client, room_id, rating=5, issue="none", **extra):
    return client.post("/api/feedback", json={
        "room_id": room_id, "rating": rating, "issue": issue, **extra,
    })


def finish(client, room):
    response = client.post("/api/reveal", json={"room_id": room["room_id"], "text": "/reveal"})
    assert response.status_code == 200


def test_feedback_after_reveal_and_once_per_room(client, create_room, isolated_app):
    room = create_room()
    assert submit(client, room["room_id"]).status_code == 409
    finish(client, room)
    response = submit(client, room["room_id"], 5, "confusing_clues")
    assert response.status_code == 201
    assert response.json() == {"status": "received"}
    assert submit(client, room["room_id"], 2).status_code == 409
    assert isolated_app.feedback_store.count() == 1
    assert isolated_app.feedback_store._items[room["room_id"]] == {
        "mystery_id": "ms-001", "rating": 5, "issue": "confusing_clues",
    }


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_all_ratings_valid(client, create_room, rating):
    room = create_room()
    finish(client, room)
    assert submit(client, room["room_id"], rating).status_code == 201


@pytest.mark.parametrize("issue", ["none", "confusing_clues", "incorrect_answer", "spoiler", "other"])
def test_issue_categories(client, create_room, issue):
    room = create_room()
    finish(client, room)
    assert submit(client, room["room_id"], issue=issue).status_code == 201


@pytest.mark.parametrize("invalid", [0, 6, -1, 3.5, True, "5", None])
def test_invalid_ratings_rejected(client, create_room, invalid, isolated_app):
    room = create_room()
    finish(client, room)
    assert submit(client, room["room_id"], invalid).status_code == 422
    assert isolated_app.feedback_store.count() == 0


def test_raw_text_and_unknown_issue_rejected(client, create_room, isolated_app):
    room = create_room()
    finish(client, room)
    for extra in ({"comment": "PRIVATE_SPOILER"}, {"text": "PRIVATE_QUESTION"}):
        assert submit(client, room["room_id"], **extra).status_code == 422
    assert submit(client, room["room_id"], issue="not_allowed").status_code == 422
    assert isolated_app.feedback_store.count() == 0


def test_nonexistent_room_and_independent_rooms(client, create_room, isolated_app):
    assert submit(client, "missing").status_code == 404
    a, b = create_room(), create_room("ms-002")
    finish(client, a)
    finish(client, b)
    assert submit(client, a["room_id"], 5).status_code == 201
    assert submit(client, b["room_id"], 1, "other").status_code == 201
    assert isolated_app.feedback_store.count() == 2


def test_bounded_capacity_and_no_public_read_api(client, create_room, isolated_app):
    isolated_app.feedback_store = FeedbackStore(capacity=1)
    a, b = create_room(), create_room("ms-002")
    finish(client, a)
    finish(client, b)
    assert submit(client, a["room_id"]).status_code == 201
    assert submit(client, b["room_id"]).status_code == 503
    assert client.get("/api/feedback").status_code == 405
    assert client.get("/api/feedback/list").status_code == 404


def test_feedback_is_process_local_and_not_analytics(client, create_room, isolated_app):
    room = create_room()
    finish(client, room)
    assert submit(client, room["room_id"], 4).status_code == 201
    assert isolated_app.analytics_recorder.enabled is False
    assert FeedbackStore().count() == 0


def test_frontend_offers_rating_only_after_game(root_dir=None):
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text()
    assert 'id="feedback-panel"' in html
    assert 'id="feedback-rating"' in html
    assert 'id="feedback-issue"' in html
    assert "function showFeedbackInChat()" in html
    assert "panel.hidden = false;" in html
    assert "panel.hidden = true;" in html
    assert "JSON.stringify({room_id:roomId, rating, issue})" in html
