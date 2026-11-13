"""Canonical Case 003: the classic matchstick / hot-air balloon desert riddle.

Keep the public mystery free of the answer. Model outputs are mocked; real
semantic acceptance should be checked against the preview AI after deployment.
"""
import pytest

CASE_ID = "ms-003"


def test_desert_case_premise_and_private_canonical_story(mystery):
    case = mystery(CASE_ID)
    assert case["mystery_id"] == CASE_ID
    assert case["title"] == "The Last Match"
    premise = case["premise_public"].lower()
    assert all(word in premise for word in ("desert", "dead", "naked", "matchstick", "footprints"))
    for spoiler in ("balloon", "draw", "parachute", "skydive"):
        assert spoiler not in premise
    summary = case["solution_summary"].lower()
    assert all(word in summary for word in ("hot-air balloon", "losing altitude", "clothes", "match", "jump", "fall"))
    assert "parachute" not in summary
    assert len(case["facts"]) >= 5
    required = [f["text"].lower() for f in case["facts"] if f["required"]]
    assert len(required) == 3
    assert any("balloon" in fact for fact in required)
    assert any("altitude" in fact for fact in required)
    assert any("jump" in fact for fact in required)
    assert any("match" in f["text"].lower() and not f["required"] for f in case["facts"])
    assert any("clothing" in f["text"].lower() and not f["required"] for f in case["facts"])
    minimum = case["minimum_solution"].lower()
    assert "balloon" in minimum and "jump" in minimum
    assert "not required" in minimum
    assert len(case["hints"]) == 2
    assert all("balloon" not in hint.lower() for hint in case["hints"])


def test_public_case_listing_and_create_room_show_replacement(client):
    catalog = client.get("/api/mysteries")
    assert catalog.status_code == 200
    item = next(c for c in catalog.json() if c["id"] == CASE_ID)
    assert item["title"] == "The Last Match"
    room = client.post("/api/create_room", json={"mystery_id":CASE_ID})
    assert room.status_code == 200
    body = room.json()
    assert body["title"] == "The Last Match"
    assert "broken matchstick" in body["premise"]
    assert "balloon" not in body["premise"].lower()


@pytest.mark.parametrize("explanation", [
    "The balloon was sinking over the desert, so he jumped out to save the others and died.",
    "Did they draw matches, and did he draw the short one and jump out of the falling balloon?",
    "He jumped from a hot air balloon losing altitude, and died when he hit the desert.",
])
def test_balloon_explanations_can_end_case_in_chat(client, create_room, moderator, isolated_app, explanation):
    completion = moderator("Solved")
    room = create_room(CASE_ID)
    answer = client.post("/api/message", json={
        "room_id":room["room_id"],"text":explanation
    })
    assert answer.status_code == 200
    assert answer.json()["solved"] is True
    assert "Correct!" in answer.json()["reply"]
    assert completion.call_count == 1
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is True


def test_single_balloon_fact_is_not_automatically_a_solution(client, create_room, moderator):
    completion = moderator("Yes")
    room = create_room(CASE_ID)
    answer = client.post("/api/message", json={
        "room_id":room["room_id"],"text":"Was he in a balloon?"
    })
    assert answer.status_code == 200
    assert answer.json()["solved"] is False
    assert completion.call_count == 1
