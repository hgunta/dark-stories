"""Fairness regressions for the actual public moderator route; no paid model calls."""
import pytest

from game import direct_yes_fact_question


@pytest.mark.parametrize("question", [
    "is it 2 fish?", "is it two fish?", "is it 2 goldfish?",
    "are they fish?", "were the victims goldfish?",
    "is the couple a pair of goldfish?",
])
def test_correct_victim_category_is_yes(client, create_room, isolated_app, question):
    room = create_room("ms-001")
    response = client.post("/api/message", json={"room_id": room["room_id"], "text": question})
    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"].startswith("Yes.")
    assert "submit your solution" in payload["reply"]
    assert payload["solved"] is False
    state = isolated_app.ROOMS[room["room_id"]]["state"]
    assert 0 in state["confirmed_true"]
    assert state["solved"] is False


@pytest.mark.parametrize("question", [
    "are they not fish?", "is it fish or a cat?",
    "were the fish in a bowl?", "does a fish tank break?",
    "is it two plants?", "is it two fisherman?",
])
def test_direct_fact_guard_cannot_misread_compound_or_negated_questions(mystery, question):
    assert direct_yes_fact_question(question, mystery("ms-001")) is None


def test_same_identity_question_cannot_change_answer(client, create_room, moderator):
    room = create_room("ms-001")
    completion = moderator("No", "Focus on something else")
    for question in ("is it two fish?", "is it two goldfish?"):
        result = client.post("/api/message", json={"room_id":room["room_id"],"text":question})
        assert result.json()["reply"].startswith("Yes.")
        assert result.json()["solved"] is False
    completion.assert_not_called()  # Exact authored true synonym bypasses uncertain AI.


def test_normal_yes_no_questions_suppress_model_hints(client, create_room, moderator):
    room = create_room("ms-001")
    moderator("No", "Think about the nature of the victims")
    result = client.post("/api/message", json={"room_id":room["room_id"],"text":"Did they drown?"})
    assert result.json() == {"reply":"No","solved":False}


def test_full_private_explanation_is_the_win_condition_offline(client, create_room):
    room = create_room("ms-001")
    guess = "The couple were two goldfish whose glass bowl broke and spilled its water, killing them."
    result = client.post("/api/private_guess", json={"room_id":room["room_id"], "guess": guess})
    assert result.status_code == 200
    assert result.json()["correct"] is True
    assert result.json()["solved"] is True
    assert result.json()["reply"] == "Correct! You solved the mystery."


def test_other_cases_keep_existing_moderator_behavior(client,create_room):
    room = create_room("ms-002")
    resp = client.post("/api/message",json={"room_id":room["room_id"],"text":"are they fish?"})
    assert resp.status_code == 200
    assert resp.json() == {"reply":"Unknown. (offline mode)","solved":False}
