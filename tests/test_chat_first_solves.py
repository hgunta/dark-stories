"""Chat-first solve regressions for all five beta cases; mocked model, no paid API calls."""
import pytest


@pytest.mark.parametrize("text", [
    "The man fell from the plane because his parachute did not open.",
    "Did the person jump off an aircraft intending to open the parachute, but it didn't end up opening?",
    "The couple were goldfish whose bowl shattered, leaving them without water.",
    "did the 2 goldfish die after the bowl fell and broke and they suffocated?",
    "did the 2 goldfish die after the bow fell and broke and they suffocated?",
    "did the fish's bowl drop, breaking the bowl, spilling the water and suffocating the fish?",
    "did their bowl drop, it broke and they died?",
])
def test_complete_theory_detection(text, isolated_app):
    from game import looks_like_complete_theory_attempt
    assert looks_like_complete_theory_attempt(text)


@pytest.mark.parametrize("theory", [
    "did the 2 goldfish die after the bowl fell and broke and they suffocated?",
    "did the 2 goldfish die after the bow fell and broke and they suffocated?",
])
def test_goldfish_complete_causal_question_can_solve(client, create_room, moderator, isolated_app, theory):
    completion = moderator("Solved")
    room = create_room("ms-001")
    response = client.post("/api/message", json={"room_id": room["room_id"], "text": theory})
    assert response.status_code == 200
    assert response.json()["solved"] is True
    assert "Correct!" in response.json()["reply"]
    assert completion.call_count == 1
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is True


def test_solve_case_button_explicit_message_routes_to_solution_judge(client, create_room, moderator):
    completion = moderator("Solved")
    room = create_room("ms-001")
    response = client.post("/api/message", json={
        "room_id":room["room_id"],
        "text":"Were they goldfish in a broken bowl?",
        "solution_attempt": True,
    })
    assert response.status_code == 200
    assert response.json()["solved"] is True
    assert completion.call_count == 1


@pytest.mark.parametrize("theory", [
    "did the fish's bowl drop, breaking the bowl, spilling the water and suffocating the fish?",
])
def test_goldfish_multi_event_question_is_judged_and_solved(client, create_room, moderator, isolated_app, theory):
    completion = moderator("Solved")
    room = create_room("ms-001")
    response = client.post("/api/message", json={"room_id": room["room_id"], "text":theory})
    assert response.status_code == 200
    assert response.json()["solved"] is True
    assert "Correct!" in response.json()["reply"]
    assert completion.call_count == 1


def test_near_solved_fallback_asks_final_judge_once(client, create_room, moderator, isolated_app):
    completion = moderator("AlmostSolved")
    first = completion.return_value
    moderator("Solved")
    second = completion.return_value
    completion.side_effect = [first,second]
    room = create_room("ms-001")
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text":"Did the fish suffocate?"
    })
    assert response.status_code == 200
    assert response.json()["solved"] is True
    assert completion.call_count == 2


def test_near_solved_partial_guess_requires_final_judge_confirmation(client, create_room, moderator):
    completion = moderator("AlmostSolved")
    first = completion.return_value
    moderator("No")
    second = completion.return_value
    completion.side_effect = [first,second]
    room = create_room("ms-001")
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text":"Did the fish suffocate?"
    })
    assert response.status_code == 200
    assert response.json()["solved"] is False
    assert response.json()["almost_solved"] is True
    assert completion.call_count == 2


def test_partial_question_not_a_full_explanation(isolated_app):
    from game import looks_like_complete_theory_attempt
    assert not looks_like_complete_theory_attempt("was this a failed parachute situation?")


@pytest.mark.parametrize("case_id,explanation", [
    ("ms-003", "The man jumped from a plane but his parachute did not open."),
    ("ms-003", "Did the person jump off an aircraft intending to open the parachute, but it didn't end up opening?"),
    ("ms-001", "The couple were two goldfish whose glass bowl shattered, leaving them without water."),
    ("ms-002", "He was too short to reach the button, so he used an umbrella on rainy days."),
    ("ex-001", "The man was counted twice, so the roll call was wrong."),
    ("ex-002", "The old note was mistaken for a current threat, triggering the response."),
])
def test_complete_explanations_can_solve_in_same_chat(client,create_room,moderator,isolated_app,case_id,explanation):
    completion=moderator("Solved")
    room=create_room(case_id)
    response=client.post("/api/message",json={"room_id":room["room_id"],"text":explanation})
    assert response.status_code==200
    assert response.json()["solved"] is True
    assert "Correct!" in response.json()["reply"]
    assert completion.call_count==1
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is True


def test_partial_discovery_does_not_end_case(client,create_room,moderator):
    completion=moderator("Yes")
    room=create_room("ms-003")
    response=client.post("/api/message",json={"room_id":room["room_id"],"text":"was this a failed parachute situation?"})
    assert response.status_code==200
    assert response.json()["solved"] is False
    assert completion.call_count==1


def test_duplicate_solution_input_is_removed():
    from pathlib import Path
    html=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    assert 'id="chat"' in html
    assert 'id="input"' in html
    assert 'id="private-guess-form"' not in html
    assert 'id="private-guess-input"' not in html
    assert "promptSolutionInChat" in html
