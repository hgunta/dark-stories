from copy import deepcopy

import pytest


@pytest.mark.parametrize("text", ["Was it an accident?", "I think I know the explanation", "/hint"])
def test_offline_questions_are_stubbed(client, create_room, text):
    room = create_room()
    response = client.post("/api/message", json={"room_id": room["room_id"], "text": text})
    assert response.status_code == 200
    assert response.json() == {"reply": "Unknown. (offline mode)", "solved": False}


@pytest.mark.parametrize("mid", ["ms-001", "ms-002", "ms-003"])
def test_hint_order_and_exhaustion(client, create_room, mystery, mid):
    room = create_room(mid)
    body = {"room_code": room["room_code"], "text": "/hint"}
    for number, hint in enumerate(mystery(mid)["hints"], 1):
        response = client.post("/api/hint", json=body)
        assert response.status_code == 200
        assert response.json() == {"reply": f"Hint {number}: {hint}", "solved": False}
    for _ in range(2):
        assert client.post("/api/hint", json=body).json() == {"reply": "No more hints.", "solved": False}


@pytest.mark.parametrize("mid", ["ms-001", "ms-002", "ms-003"])
def test_reveal_is_repeatable_and_ends_game(client, create_room, mystery, mid):
    room = create_room(mid)
    body = {"room_id": room["room_id"], "text": "/reveal"}
    for _ in range(2):
        response = client.post("/api/reveal", json=body)
        assert response.status_code == 200
        assert response.json() == {"reply": f"🟥 Solution revealed: {mystery(mid)['solution_summary']}", "solved": True}
    assert client.get(f"/api/join/{room['room_code']}").json()["solved"] is True
    assert client.post("/api/message", json=body).json() == {"reply": "Game over. Create a new room.", "solved": True}


@pytest.mark.parametrize("endpoint", ["message", "hint", "reveal"])
def test_text_required_even_for_hint_and_reveal(client, create_room, endpoint):
    room = create_room()
    assert client.post(f"/api/{endpoint}", json={"room_id": room["room_id"]}).status_code == 422


def test_rooms_start_empty(isolated_app):
    assert isolated_app.ROOMS == {}
    assert isolated_app.CODE_MAP == {}


def test_same_mystery_rooms_have_independent_state(client, create_room, moderator, isolated_app, mystery):
    first, second = create_room(), create_room()
    assert first["room_id"] != second["room_id"]
    assert first["room_code"] != second["room_code"]
    body = {"room_id": first["room_id"], "text": "Question?"}
    moderator("Yes", indices=[0])
    client.post("/api/message", json=body)
    moderator("No", indices=[1])
    client.post("/api/message", json=body)
    client.post("/api/hint", json=body)
    client.post("/api/reveal", json=body)
    first_state = deepcopy(isolated_app.ROOMS[first["room_id"]]["state"])
    assert first_state == {"asked": 2, "hints_used": 1, "solved": True,
                           "confirmed_true": {0}, "confirmed_false": {1}}
    assert isolated_app.ROOMS[second["room_id"]]["state"] == {
        "asked": 0, "hints_used": 0, "solved": False, "confirmed_true": set(), "confirmed_false": set()}
    second_body = {"room_id": second["room_id"], "text": "/hint"}
    assert client.post("/api/hint", json=second_body).json() == {
        "reply": f"Hint 1: {mystery('ms-001')['hints'][0]}", "solved": False}
    assert client.get(f"/api/join/{second['room_code']}").json()["solved"] is False
    assert isolated_app.ROOMS[first["room_id"]]["state"] == first_state
