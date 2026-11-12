"""Regression tests for correct causal hypotheses in normal chat. No paid calls."""
import pytest

THEORY_1 = ("so the person's name was present twice and she crossed one off. "
            "which meant a fifth resident was actually not listed in the list "
            "but not rescued so needed to be rescued and hence firefighters went back in?")
THEORY_2 = ("there were 5 people inside, only 4 were rescued - those standing outside. "
            "but the firefighters incorrectly accounted for 5 because they had the "
            "same person listed twice. as soon as they realized that they double "
            "counted one person, they went back in to rescue the other person")

@pytest.mark.parametrize("theory", [THEORY_1, THEORY_2])
def test_complete_user_theory_in_regular_chat_earns_win(
    client,create_room,moderator,isolated_app,theory
):
    room=create_room("ex-001")
    completion=moderator("Solved")
    r=client.post("/api/message",json={"room_id":room["room_id"],"text":theory})
    assert r.status_code==200
    assert r.json()=={"reply":"✅ Correct! You solved the mystery.","solved":True}
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is True
    assert completion.call_count==1
    sent=completion.call_args.kwargs["messages"][0]["content"]
    assert "Do not demand incidental" in sent
    assert "Minimum sufficient explanation" in sent
    room_state=client.get("/api/room_state/"+room["room_code"]).json()
    assert room_state["events"]==[{"seq":1,"kind":"solved"}]
    assert theory not in str(room_state)

def test_partial_question_cannot_end_case(client,create_room,moderator):
    room=create_room("ex-001")
    completion=moderator("Yes")
    r=client.post("/api/message",json={"room_id":room["room_id"],
                                      "text":"Was someone counted twice?"})
    assert r.json()["solved"] is False
    assert completion.call_count==1

def test_false_long_theory_stays_unsolved(client,create_room,moderator,isolated_app):
    room=create_room("ex-001")
    from types import SimpleNamespace
    import json
    completion=moderator("No")
    def label_response(label):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=json.dumps({
                "kind":"hypothesis","label":label,"short_explanation":"","fact_indices":[]
            })))]))])
    completion.side_effect=[label_response("No"),label_response("No")]
    false=("There were five different people rescued, because the woman crossed "
           "off her name to make the firefighters search again as a prank.")
    r=client.post("/api/message",json={"room_id":room["room_id"],"text":false})
    assert r.status_code==200
    assert r.json()["solved"] is False
    assert completion.call_count==2
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is False

def test_minimum_solution_has_no_surname_password():
    from game import load_mystery
    data=load_mystery("ex-001")
    assert "double count" in data["minimum_solution"]
    assert "irrelevant" in data["minimum_solution"]
    assert data["facts"][4]["required"] is False

def test_ui_shows_reward_and_rating():
    from pathlib import Path
    page=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    assert "Case complete. How satisfying was the reveal?" in page
    assert "el('feedback-panel').hidden = false" in page

def test_short_causal_theories_are_eligible_without_password_words():
    from game import looks_like_complete_theory_attempt
    assert looks_like_complete_theory_attempt(
        "They counted the same person twice, so someone else was missing.")
    assert looks_like_complete_theory_attempt(
        "A survivor was counted twice. Someone else was missing.")
    assert looks_like_complete_theory_attempt(
        "Could they have counted her twice, so another person remained missing?")
    assert not looks_like_complete_theory_attempt("Was one person counted twice?")
    assert not looks_like_complete_theory_attempt("Was the fifth person outside?")
    assert not looks_like_complete_theory_attempt("/hint")
