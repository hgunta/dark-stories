"""Regression checks for discovery acknowledgment and semantic moderation rules.

These use a mocked model: live model truthfulness is evaluated separately.
"""


def test_important_discovery_gets_next_step_without_spoiler(client, create_room, moderator):
    room = create_room("ms-001")
    completion = moderator("Yes", nudge="", indices=[0])
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Are they two fish?"
    })
    assert response.status_code == 200
    assert response.json() == {
        "reply": "Yes. Important clue! Keep connecting the clues, or propose a full explanation.",
        "solved": False,
    }
    system_prompt = completion.call_args.kwargs["messages"][0]["content"]
    assert '"Are there two fish?" is Yes' in system_prompt
    assert "Never answer No just because" in system_prompt


def test_unimportant_yes_stays_short(client, create_room, moderator):
    room = create_room("ms-001")
    moderator("Yes", indices=[4])
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Was there foul play?"
    })
    assert response.json() == {"reply": "Yes", "solved": False}


def test_duplicate_discovery_reminds_player_what_to_do(client, create_room, moderator):
    room = create_room("ms-001")
    moderator("Yes", indices=[0])
    for _ in range(2):
        response = client.post("/api/message", json={
            "room_id": room["room_id"], "text": "Were they fish?"
        })
        assert response.json()["reply"].startswith("Yes. Important clue!")
        assert response.json()["solved"] is False


def test_no_does_not_get_discovery_congratulations(client, create_room, moderator):
    room = create_room("ms-001")
    moderator("No", indices=[0])
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Were they people?"
    })
    assert response.json() == {"reply": "No", "solved": False}


def test_unknown_fact_index_does_not_trigger_guidance(client, create_room, moderator):
    room = create_room("ms-001")
    moderator("Yes", indices=[999])
    response = client.post("/api/message", json={
        "room_id": room["room_id"], "text": "Is something relevant?"
    })
    assert response.json() == {"reply": "Yes", "solved": False}
