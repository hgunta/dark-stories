"""Chat-first solve regressions for all five beta cases; mocked model, no paid API calls."""
import pytest
from game import looks_like_complete_theory_attempt


@pytest.mark.parametrize("text", [
    "The man fell from the plane because his parachute did not open.",
    "Did the person jump off an aircraft intending to open the parachute, but it didn't end up opening?",
    "The couple were goldfish whose bowl shattered, leaving them without water.",
])
def test_complete_theory_detection(text):
    assert looks_like_complete_theory_attempt(text)


def test_partial_question_not_a_full_explanation():
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
