from pathlib import Path
import pytest


IDS = sorted(p.stem for p in (Path(__file__).resolve().parents[1] / "backend" / "mysteries").glob("ms-*.json"))


def test_mystery_listing_exposes_only_public_catalog(client, mystery):
    response = client.get("/api/mysteries")
    assert response.status_code == 200
    assert response.json() == [{"id": mid, "title": mystery(mid)["title"]} for mid in IDS]


@pytest.mark.parametrize("mid", IDS)
def test_create_and_join_room(client, create_room, mystery, mid):
    room = create_room(mid)
    content = mystery(mid)
    assert set(room) == {"room_id", "room_code", "premise", "title"}
    assert len(room["room_id"]) == 8
    assert len(room["room_code"]) == 4
    assert set(room["room_code"]) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ")
    assert room["premise"] == content["premise_public"]
    assert room["title"] == content["title"]
    joined = client.get(f"/api/join/{room['room_code'].lower()}")
    assert joined.status_code == 200
    assert joined.json() == {**{k: room[k] for k in ("room_id", "room_code", "title")},
                             "premise": content["premise_public"], "mystery_id": mid, "solved": False}


def test_default_mystery(client, mystery):
    response = client.post("/api/create_room", json={})
    assert response.status_code == 200
    assert response.json()["title"] == mystery("ms-001")["title"]


def test_unknown_join(client):
    response = client.get("/api/join/ZZZZ")
    assert response.status_code == 404
    assert response.json() == {"detail": "Room not found"}


@pytest.mark.parametrize("endpoint", ["message", "hint", "reveal"])
@pytest.mark.parametrize("selector", [{"room_id": "missing"}, {"room_code": "ZZZZ"}, {}])
def test_unknown_room_actions(client, endpoint, selector):
    response = client.post(f"/api/{endpoint}", json={**selector, "text": "Question?"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Room not found"}


def test_room_selectors_and_id_precedence(client, create_room, mystery):
    first, second = create_room(), create_room("ms-002")
    response = client.post("/api/message", json={"room_id": first["room_id"],
                           "room_code": second["room_code"], "text": "/premise"})
    assert response.json()["reply"] == f"Premise: {mystery('ms-001')['premise_public']}"
    response = client.post("/api/message", json={"room_id": "missing",
                           "room_code": f" {second['room_code'].lower()} ", "text": "/premise"})
    assert response.json()["reply"] == f"Premise: {mystery('ms-002')['premise_public']}"
