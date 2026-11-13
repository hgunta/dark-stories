"""SDK I/O is mocked; classifier parsing and API solve logic remain real."""

import json
from types import SimpleNamespace

import pytest


def ask(client, room):
    response = client.post("/api/message", json={"room_id": room["room_id"], "text": "Was it an accident?"})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("label,nudge,reply", [
    ("Yes", "", "Yes"), ("No", "", "No"),
    ("Irrelevant", "", "Irrelevant"), ("Unknown", "", "Unknown"),
    ("AlmostSolved", "", "Yes. You're close — explain how the pieces fit together."),
    ("Yes", "Consider another angle", "Yes"),
    ("AskYesNo", "Try again", "Cannot answer. Please ask a yes/no question."),
    ("unexpected", "", "Unknown. Please ask a yes/no question."),
    ("Yes", "It was a fish", "Yes"),  # Filtered nudge becomes Irrelevant and is omitted.
])
def test_mocked_moderator_labels(client, create_room, moderator, label, nudge, reply):
    room = create_room()
    completion = moderator(label, nudge)
    expected = {"reply": reply, "solved": False}
    if label == "AlmostSolved":
        expected["almost_solved"] = True
    assert ask(client, room) == expected
    completion.assert_called_once()
    kwargs = completion.call_args.kwargs
    assert kwargs["model"] == "gpt-4.1-mini"
    assert kwargs["tools"][0]["function"]["name"] == "moderator_decide"
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1] == {"role": "user", "content": "Was it an accident?"}


def test_question_form_solved_label_requires_explanation(client, create_room, moderator):
    room = create_room()
    completion = moderator("Solved")
    assert ask(client, room) == {
        "reply": "Yes. You're close — explain how the pieces fit together.",
        "solved": False, "almost_solved": True
    }
    completion.assert_called_once()


def test_complete_public_statement_prompts_explicit_solution(client, create_room, moderator):
    room = create_room()
    completion = moderator("Solved")
    response = client.post("/api/message", json={
        "room_id": room["room_id"],
        "text": "The couple were goldfish that died when their bowl broke and spilled its water."
    })
    assert response.json() == {
        "reply": "Yes. You're close — explain how the pieces fit together.",
        "solved": False, "almost_solved": True
    }
    # The explicit solution form is the only way to finish without revealing.
    # Reuse the mock to model the separate final-solution evaluation.
    correct = client.post("/api/private_guess", json={
        "room_id": room["room_id"],
        "guess": "The couple were two goldfish whose glass bowl broke and spilled its water, killing them."
    })
    assert correct.status_code == 200
    assert correct.json()["solved"] is True
    assert completion.call_count == 2


@pytest.mark.parametrize("mid", ["ms-001", "ms-002", "ms-003"])
def test_required_fact_confirmation_solves_without_optional_facts(client, create_room, moderator, mystery, isolated_app, mid):
    room = create_room(mid)
    content = mystery(mid)
    required = [i for i, fact in enumerate(content["facts"]) if fact.get("required", True)]
    for step, index in enumerate(required):
        moderator("Yes", indices=[index])
        response = ask(client, room)
        assert response["solved"] is False
    assert response["reply"] == (
        "Yes. You're close — explain how the pieces fit together."
        if step == len(required) - 1 else "Yes"
    )
    state = isolated_app.ROOMS[room["room_id"]]["state"]
    assert state["confirmed_true"] == set(required)
    assert state["solved"] is False


def test_no_and_duplicate_yes_do_not_complete_required_facts(client, create_room, moderator, isolated_app):
    room = create_room()
    moderator("No", indices=[0, 1, 2])
    assert ask(client, room)["solved"] is False
    moderator("Yes", indices=[0])
    assert ask(client, room)["solved"] is False
    assert ask(client, room)["solved"] is False
    state = isolated_app.ROOMS[room["room_id"]]["state"]
    assert state["confirmed_false"] == {0, 1, 2}
    assert state["confirmed_true"] == {0}


def test_multiple_fact_indices_can_solve_in_one_question(client, create_room, moderator):
    room = create_room()
    moderator("Yes", indices=[0, 1, 2])
    result = ask(client, room)
    assert result["solved"] is False
    assert result["almost_solved"] is True


def test_absent_tool_call_falls_back_to_unknown(client, create_room, moderator):
    room = create_room()
    completion = moderator()
    completion.return_value.choices[0].message.tool_calls = []
    assert ask(client, room) == {"reply": "Unknown", "solved": False}


@pytest.mark.parametrize("indices,expected", [("invalid", set()), ([0, "1", None, 99], {0, 99})])
def test_current_fact_index_filtering(client, create_room, moderator, isolated_app, indices, expected):
    # Existing limitation: integer indices outside the content bounds are retained.
    room = create_room()
    moderator("Yes", indices=indices)
    assert ask(client, room)["solved"] is False
    assert isolated_app.ROOMS[room["room_id"]]["state"]["confirmed_true"] == expected


@pytest.mark.parametrize("failure", ["malformed_json", "upstream_error"])
def test_moderation_failures_return_retryable_safe_503(client, create_room, moderator, failure):
    room = create_room()
    completion = moderator()
    if failure == "malformed_json":
        completion.return_value.choices[0].message.tool_calls = [
            SimpleNamespace(function=SimpleNamespace(arguments="not-json"))]
    else:
        completion.side_effect = RuntimeError("PRIVATE_UPSTREAM_FAILURE")
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Was it an accident?"})
    assert response.status_code == 503
    assert response.json() == {"detail": "The moderator is unavailable. Please try again."}
    assert "PRIVATE" not in response.text
    # The game remains open and can recover on a later request.
    completion.side_effect = None
    moderator("No")
    assert ask(client, room)["solved"] is False


def test_missing_mystery_returns_safe_404(client):
    response = client.post("/api/create_room", json={"mystery_id": "missing"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Mystery not found"}


def test_unknown_cannot_leak_solution_through_nudge(client, create_room, moderator):
    room = create_room("ms-009")
    moderator("Unknown", "Ask whether someone was steering from elsewhere.")
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Was a crew member involved?"
    })
    assert response.status_code == 200
    assert response.json() == {"reply": "Unknown", "solved": False}


def test_ask_yes_no_cannot_leak_solution_through_nudge(client, create_room, moderator):
    room = create_room("ms-009")
    moderator("AskYesNo", "Try asking if someone used remote controls.")
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "How did the ferry operate?"
    })
    assert response.status_code == 200
    assert response.json() == {
        "reply": "Cannot answer. Please ask a yes/no question.", "solved": False
    }


def test_short_core_solution_question_can_end_case(client, create_room, moderator, mystery):
    room = create_room("ms-009")
    moderator("Solved")
    response = client.post("/api/message", json={
        "room_id": room["room_id"],
        "text": "Was the ferry steered remotely from a shore station?"
    })
    assert response.status_code == 200
    assert response.json() == {
        "reply": "Yes. You're close — explain how the pieces fit together.",
        "solved": False, "almost_solved": True
    }


def test_partial_identity_question_remains_yes_not_solved(client, create_room, moderator):
    room = create_room("ms-008")
    moderator("Yes", indices=[0])
    response = client.post("/api/message", json={
        "room_id": room["room_id"],
        "text": "Was the music prerecorded?"
    })
    assert response.status_code == 200
    assert response.json() == {"reply": "Yes", "solved": False}
