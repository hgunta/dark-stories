"""Spoiler-free nonterminal progress tests; model I/O is mocked."""
from pathlib import Path

import pytest


NEAR = "Yes. You're close — explain how the pieces fit together."


@pytest.mark.parametrize("mid,text", [
    ("ms-002", "Could the message have been a warning?"),
    ("ms-003", "Did somebody misunderstand the situation?"),
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
    room = create_room("ms-001")
    moderator("AlmostSolved")
    for _ in range(3):
        result = client.post("/api/message", json={
            "room_id": room["room_id"], "text": "Is remote control involved?"
        })
        assert result.json()["solved"] is False
    assert isolated_app.ROOMS[room["room_id"]]["state"]["solved"] is False


def test_unknown_with_model_nudge_is_never_almost_solved(client, create_room, moderator):
    room = create_room("ms-001")
    moderator("Unknown", nudge="Ask if it is remotely operated")
    result = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Was the weather warm?"
    })
    assert result.json() == {"reply": "Unknown", "solved": False}


def test_ui_only_reveals_progress_cta_for_explicit_almost_solved_signal():
    html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text()
    css = (Path(__file__).resolve().parents[1] / "frontend" / "case-stamp.css").read_text()
    assert 'id="almost-solved" class="almost-solved"' in html
    assert 'id="almost-solved-action"' in html
    assert 'if (data.almost_solved && !data.solved)' in html
    assert "el('almost-solved-action')?.addEventListener('click',promptSolutionInChat)" in html
    assert "el('almost-solved').hidden = true;" in html
    assert ".almost-solved" in css
