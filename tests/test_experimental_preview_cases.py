"""Preview-only experimental case routing, presentation, and solve contract."""
from pathlib import Path

def test_experimental_cases_are_separate_from_main_library(client):
    normal = client.get("/api/mysteries")
    assert normal.status_code == 200
    assert not any(x["id"].startswith("ex-") for x in normal.json())
    experimental = client.get("/api/experimental_mysteries")
    assert experimental.status_code == 200
    items = experimental.json()
    assert [x["id"] for x in items] == ["ex-001", "ex-002"]
    assert {x["title"] for x in items} == {"The Fifth Name", "The Rehearsal Note"}
    assert all("experimental" in x["tags"] for x in items)
    assert all("solution" not in str(x).lower() for x in items)

def test_both_experiments_create_and_reveal(client, create_room):
    for mid in ("ex-001", "ex-002"):
        room = create_room(mid)
        assert room["title"] in ("The Fifth Name","The Rehearsal Note")
        assert room["premise"]
        assert "solution_summary" not in room
        result = client.post("/api/reveal",json={"room_id":room["room_id"],"text":"/reveal"})
        assert result.status_code == 200
        assert result.json()["solved"] is True
        assert result.json()["reply"].startswith("🟥 Solution revealed:")

def test_correct_full_theory_ends_experiment(client, create_room):
    from game import load_mystery
    for mid in ("ex-001", "ex-002"):
        room = create_room(mid)
        first = load_mystery(mid)["acceptable_solutions"][0]
        result = client.post("/api/private_guess",json={
            "room_id":room["room_id"],"guess":first
        })
        assert result.status_code == 200
        assert result.json()["correct"] is True
        assert result.json()["solved"] is True

def test_true_partial_question_and_near_solve_do_not_end_case(client, create_room, moderator):
    room = create_room("ex-001")
    moderator("Yes",indices=[0])
    reply=client.post("/api/message",json={"room_id":room["room_id"],
                                           "text":"Was one person counted twice?"})
    assert reply.status_code==200
    assert reply.json()["reply"]=="Yes"
    assert reply.json()["solved"] is False
    moderator("AlmostSolved")
    near=client.post("/api/message",json={"room_id":room["room_id"],
                                          "text":"I think a name was duplicated"})
    assert near.json()["almost_solved"] is True
    assert near.json()["solved"] is False

def test_additional_stories_join_the_normal_case_library():
    html=(Path(__file__).resolve().parents[1]/"frontend"/"index.html").read_text()
    assert 'id="case-grid"' in html
    assert 'id="experimental-section"' not in html
    assert 'id="experimental-grid"' not in html
    assert 'id="browse-experiments"' not in html
    assert "/api/experimental_mysteries" in html
    assert "renderExperimentalCases(items)" in html
    assert "function renderCombinedLibrary()" in html
    assert "const items = [...AVAILABLE_CASES, ...EXPERIMENTAL_CASES]" in html
    assert "card.className = 'case-tile'" in html
    assert "createRoom(item.id)" in html
    assert "el('case-grid').innerHTML" not in html
