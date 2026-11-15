"""Spoiler-free nonterminal progress tests; model I/O is mocked."""
from pathlib import Path

import pytest


NEAR = "Yes. You're close — keep investigating the missing link."


@pytest.mark.parametrize("mid,text", [
    ("ms-002", "Was the man short?"),
    ("ms-003", "Was he carrying a broken matchstick?"),
    ("ms-001", "Did their fishbowl break?"),
])
def test_almost_solved_prompts_without_ending(client, create_room, moderator, isolated_app, mystery, mid, text):
    room = create_room(mid)
    moderator("AlmostSolved", nudge="SECRET: do not leak the answer")
    result = client.post("/api/message", json={
        "room_id": room["room_id"], "text": text
    })
    assert result.status_code == 200
    assert result.json() == {"reply": NEAR, "solved": False, "almost_solved": True}
    assert mystery(mid)["solution_summary"] not in result.text
    assert "SECRET" not in result.text
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is False


def test_not_solved_for_single_fish_category(client, create_room, isolated_app):
    room = create_room("ms-001")
    result = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "is it two fish?"
    })
    assert result.status_code == 200
    assert result.json()["solved"] is False
    assert result.json().get("almost_solved") is None


def test_repeated_near_discovery_does_not_complete_case(client, create_room, moderator, isolated_app):
    room = create_room("ms-002")
    moderator("AlmostSolved")
    for _ in range(3):
        result = client.post("/api/message", json={
            "room_id": room["room_id"], "text": "Was the weather unusually bad?"
        })
        assert result.json()["solved"] is False
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is False


def test_unknown_with_model_nudge_is_never_almost_solved(client, create_room, moderator):
    room = create_room("ms-002")
    moderator("Unknown", nudge="Ask if the rain matters")
    result = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Was the weather warm?"
    })
    assert result.json() == {"reply": "Unknown", "solved": False}


def test_ui_uses_plain_conversation_instead_of_a_redundant_solution_form():
    html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text()
    assert 'id="chat"' in html
    assert 'id="case-opening-question"' in html
    assert 'id="almost-solved"' not in html
    assert 'id="almost-solved-action"' not in html
    assert 'id="open-solution"' not in html
