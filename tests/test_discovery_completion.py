"""A case can close after independently confirming its full causal chain.

The moderator and AI client are stubbed. No paid API calls or hidden solutions
are ever sent to the browser.
"""
import pytest


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
            "text": f"Is observation number {i + 1} correct?"
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
            "room_id": room["room_id"], "text": "Is that observation correct?"
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
            "room_id": room["room_id"], "text": "Is this observation true?"
        })
    for label, indices in (("No", [3]), ("Yes", []), ("Yes", [999]), ("Unknown", [3])):
        moderator(label, indices=indices)
        reply = client.post("/api/message", json={
            "room_id": room["room_id"], "text": "What about this detail?"
        })
        assert reply.status_code == 200
        assert reply.json()["solved"] is False
    assert not isolated_app.ROOMS[room["room_id"]]["state"]["solved"]


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
