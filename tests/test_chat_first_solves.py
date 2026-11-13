"""Regression coverage: complete theories solve directly in the one chat input.

Mocks model I/O; no paid API calls.
"""
import pytest

from game import looks_like_complete_theory_attempt


@pytest.mark.parametrize("theory", [
    "The parachute did not open during his skydive, so he died.",
    "Did the person jump from an aircraft intending to open the parachute, but it never opened?",
    "The victim was a goldfish whose bowl shattered, leaving it without water.",
    "did the 2 goldfish die after the bowl fell and broke and they suffocated?",
    "did the 2 goldfish die after the bow fell and broke and they suffocated?",
    "did the fish's bowl drop, breaking the bowl, spilling the water and suffocating the fish?",
    "did their bowl drop, it broke and they died?",
])
def test_complete_theory_detection(theory):
    assert looks_like_complete_theory_attempt(theory)


@pytest.mark.parametrize("theory", [
    "did the 2 goldfish die after the bowl fell and broke and they suffocated?",
    "did the 2 goldfish die after the bow fell and broke and they suffocated?",
    "did the fish's bowl drop, breaking the bowl, spilling the water and suffocating the fish?",
])
def test_case_001_question_form_full_explanation_solves(client, create_room, moderator, isolated_app, theory):
    completion = moderator("Solved")
    room = create_room("ms-001")
    result = client.post("/api/message", json={"room_id":room["room_id"],"text":theory})
    assert result.status_code == 200
    assert result.json()["solved"] is True
    assert "Correct!" in result.json()["reply"]
    assert completion.call_count == 1
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is True


def test_near_solved_general_moderation_gets_independent_final_check(client, create_room, moderator, isolated_app):
    # A solution with no recognised causal connector can still be caught
    # if the ordinary moderator says AlmostSolved; don't loop forever.
    completion = moderator("AlmostSolved")
    first = completion.return_value
    moderator("Solved")
    second = completion.return_value
    completion.side_effect = [first, second]
    room = create_room("ms-001")
    response = client.post("/api/message", json={
        "room_id":room["room_id"], "text":"Did the fish bowl shatter and the fish suffocate?"
    })
    assert response.status_code == 200
    assert response.json()["solved"] is True
    assert completion.call_count == 2


def test_partial_near_solve_does_not_end_unless_final_judge_agrees(client, create_room, moderator):
    completion = moderator("AlmostSolved")
    first = completion.return_value
    moderator("No")
    second = completion.return_value
    completion.side_effect = [first, second]
    room = create_room("ms-001")
    response = client.post("/api/message", json={
        "room_id":room["room_id"], "text":"Did the fish bowl shatter and the fish suffocate?"
    })
    assert response.status_code == 200
    assert response.json()["solved"] is False
    assert response.json()["almost_solved"] is True
    assert completion.call_count == 2


def test_solve_case_action_routes_question_to_final_judge(client, create_room, moderator, isolated_app):
    completion = moderator("Solved")
    room = create_room("ms-001")
    result = client.post("/api/message", json={
        "room_id":room["room_id"],
        "text":"Were they goldfish in a broken bowl?",
        "solution_attempt": True
    })
    assert result.status_code == 200
    assert result.json()["solved"] is True
    assert completion.call_count == 1


def test_short_partial_question_is_not_final_theory():
    assert not looks_like_complete_theory_attempt("was this a failed parachute situation?")


@pytest.mark.parametrize("mid,theory", [
    ("ms-003", "The man jumped from a plane but his parachute did not open."),
    ("ms-003", "Did the person jump off an aircraft with the intention of opening the parachute, but it didn't end up opening?"),
    ("ms-001", "The couple were two goldfish whose bowl shattered, leaving them without water."),
    ("ms-002", "He was too short to reach the button, so he used an umbrella on rainy days."),
])
def test_original_cases_can_be_solved_in_chat(client,create_room,moderator,isolated_app,mid,theory):
    completion = moderator("Solved")
    room = create_room(mid)
    result = client.post("/api/message",json={"room_id":room["room_id"],"text":theory})
    assert result.status_code == 200
    assert result.json()["solved"] is True
    assert "Correct!" in result.json()["reply"]
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is True
    assert completion.call_count == 1
    assert client.post("/api/message",json={"room_id":room["room_id"],"text":"anything"}).json()["solved"] is True


def test_partial_fact_not_auto_solved(client,create_room,moderator):
    completion=moderator("Yes")
    room=create_room("ms-003")
    result=client.post("/api/message",json={"room_id":room["room_id"],"text":"Was this a failed parachute situation?"})
    assert result.status_code==200
    assert result.json()["solved"] is False
    assert completion.call_count == 1


def test_incomplete_theory_is_not_automatically_accepted(client,create_room,moderator):
    moderator("No")
    room=create_room("ms-003")
    result=client.post("/api/message",json={"room_id":room["room_id"],"text":"He jumped from somewhere, but maybe not a plane."})
    assert result.status_code==200
    assert result.json()["solved"] is False


def test_single_chat_composer_no_second_solution_form():
    from pathlib import Path
    page=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    assert 'id="chat"' in page
    assert 'id="input"' in page
    assert 'id="game-options"' not in page
    assert 'id="private-guess-input"' not in page
    assert "promptSolutionInChat" in page
