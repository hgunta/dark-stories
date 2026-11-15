"""A case can close after independently confirming its full causal chain.

The moderator and AI client are stubbed. No paid API calls or hidden solutions
are ever sent to the browser.
"""
import pytest

# Required questions must actually mention each discovery, independently of
# what private fact indices the AI guesses.
DISCOVERY_QUESTIONS = {
    "ms-001": [
        "Were the victims fish?",
        "Did the water come from their bowl?",
        "Did the fishbowl break?",
        "Did the fish die because they were without water?",
    ],
    "ms-002": [
        "Was the man short?",
        "Could he not reach the 10th floor button?",
        "Did he carry an umbrella?",
        "Did he use the umbrella to reach the button?",
    ],
    "ms-003": [
        "Was he traveling in a balloon?",
        "Was the balloon losing altitude?",
        "Did he jump from the balloon and fall?",
    ],
}


@pytest.mark.parametrize("case_id", ["ms-001", "ms-002", "ms-003"])
def test_confirmed_discoveries_solve_without_repeating_theory(
    client, create_room, moderator, isolated_app, mystery, case_id
):
    room = create_room(case_id)
    facts = isolated_app.CURATED_DISCOVERY_CHAINS[case_id]
    assert len(facts) >= 2
    for i, fact_index in enumerate(facts):
        moderator("Yes", indices=[fact_index])
        response = client.post("/api/message", json={
            "room_id": room["room_id"],
            "text": DISCOVERY_QUESTIONS[case_id][i]
        })
        assert response.status_code == 200
        assert response.json()["solved"] is (i == len(facts) - 1)
        if i < len(facts) - 1:
            assert "Correct! You solved" not in response.text

    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"]
    assert "Correct! You solved" in response.json()["reply"]


def test_missing_causes_do_not_solve_early(client, create_room, moderator, isolated_app):
    room = create_room("ms-001")
    # Fish + bowl facts alone do not establish the cause of death.
    for index in isolated_app.CURATED_DISCOVERY_CHAINS["ms-001"][:-1]:
        moderator("Yes", indices=[index])
        response = client.post("/api/message", json={
            "room_id": room["room_id"], "text": DISCOVERY_QUESTIONS["ms-001"][index]
        })
        assert response.status_code == 200
        assert response.json()["solved"] is False


def test_wrong_or_unmapped_question_never_completes_chain(
    client, create_room, moderator, isolated_app
):
    room = create_room("ms-002")
    for index in (0, 1, 2):
        moderator("Yes", indices=[index])
        client.post("/api/message", json={
            "room_id": room["room_id"], "text": DISCOVERY_QUESTIONS["ms-002"][index]
        })
    for label, indices in (("No", [3]), ("Yes", []), ("Yes", [999]), ("Unknown", [3])):
        moderator(label, indices=indices)
        reply = client.post("/api/message", json={
            "room_id": room["room_id"], "text": "What about this detail?"
        })
        assert reply.status_code == 200
        assert reply.json()["solved"] is False
    assert not isolated_app.ROOMS[room["room_id"]]["state"]["solved"]


def test_elevator_short_question_cannot_auto_solve_even_with_overmapped_ai(
    client, create_room, moderator, isolated_app
):
    room = create_room("ms-002")
    # Reproduces the false win: the model over-claims every private fact.
    moderator("Yes", indices=[0, 1, 2, 3])
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Was the man short?"
    })
    assert response.status_code == 200
    assert response.json()["solved"] is False
    assert response.json()["reply"] == "Yes"
    state = isolated_app.ROOMS[room["room_id"]]["state"]
    assert state["confirmed_true"] == {0}
    assert state["solved"] is False


def test_elevator_cannot_finish_without_umbrella_even_with_many_yes_answers(
    client, create_room, moderator, isolated_app
):
    room = create_room("ms-002")
    for question in (
        "Was the man short?",
        "Was he not tall enough?",
        "Could he not reach the 10th floor button?",
        "Was the 10th-floor button too high?",
    ):
        moderator("Yes", indices=[0, 1, 2, 3])
        response = client.post("/api/message", json={
            "room_id": room["room_id"], "text": question
        })
        assert response.status_code == 200
        assert response.json()["solved"] is False
    assert not ({2, 3} & isolated_app.ROOMS[room["room_id"]]["state"]["confirmed_true"])


def test_elevator_pronoun_followup_credits_umbrella_mechanism(
    client, create_room, moderator
):
    room = create_room("ms-002")
    for question, index in (
        ("Was the man short?", 0),
        ("Was he unable to reach the 10th-floor button?", 1),
        ("Did he have an umbrella?", 2),
        ("Did he use it to press the button?", 3),
    ):
        moderator("Yes", indices=[0, 1, 2, 3])
        response = client.post("/api/message", json={
            "room_id": room["room_id"], "text": question
        })
        assert response.status_code == 200
        assert response.json()["solved"] is (index == 3)


def test_single_key_fact_is_not_a_solution(client, create_room, moderator):
    room = create_room("ms-003")
    moderator("Yes", indices=[0])
    reply = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Was there a balloon?"
    })
    assert reply.status_code == 200
    assert reply.json()["solved"] is False


def test_curated_rubric_is_private(client, create_room, isolated_app, mystery):
    room = create_room("ms-002")
    assert "discovery_completion_indices" not in room
    assert "umbrella" not in room["premise"].lower()
    mystery_data = mystery("ms-002")
    assert "discovery_completion_indices" not in mystery_data
    assert len(isolated_app.CURATED_DISCOVERY_CHAINS["ms-002"]) == 4
