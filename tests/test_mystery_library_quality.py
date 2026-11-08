"""Editorial safeguards and playable API coverage for the expanding case library.

These checks catch structural defects and obvious spoiler leaks. They do not
prove that a human finds the mystery fair, original, or satisfying.
"""
import json
import re
from datetime import date, timedelta

from backend.daily import challenge_for
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "backend" / "mysteries"
FILES = sorted(ROOT.glob("ms-*.json"))
EXPECTED_NEW = {f"ms-{i:03d}" for i in range(4, 13)}


def all_cases():
    return [(path.stem, json.loads(path.read_text(encoding="utf-8"))) for path in FILES]


def test_full_first_content_pack_present_and_distinct():
    entries = all_cases()
    assert len(entries) >= 12
    ids = [data["mystery_id"] for _, data in entries]
    assert set(ids) == {f"ms-{i:03d}" for i in range(1, 13)}
    assert EXPECTED_NEW.issubset(ids)
    assert len(ids) == len(set(ids))
    assert len({data["title"].lower() for _, data in entries}) == len(entries)
    assert len({data["premise_public"].lower() for _, data in entries}) == len(entries)


@pytest.mark.parametrize("mid,data", all_cases())
def test_schema_and_editorial_baseline(mid, data):
    assert set(data) == {
        "mystery_id", "title", "premise_public", "solution_summary", "facts",
        "forbidden_reveals", "acceptable_solutions", "hints", "metadata",
    }
    assert data["mystery_id"] == mid
    assert re.fullmatch(r"ms-\d{3}", mid)
    assert len(data["title"].strip()) >= 8
    assert len(data["premise_public"].strip()) >= 40
    assert len(data["solution_summary"].strip()) >= 50
    assert len(data["facts"]) >= 3
    assert sum(1 for f in data["facts"] if f["required"]) >= 3
    assert all(
        isinstance(f, dict) and set(f) == {"text", "required"}
        and isinstance(f["text"], str) and len(f["text"].strip()) >= 12
        and isinstance(f["required"], bool)
        for f in data["facts"]
    )
    assert len(data["hints"]) >= 2
    assert len(data["forbidden_reveals"]) >= 3
    assert len(data["acceptable_solutions"]) >= 2
    assert all(isinstance(v, str) and v.strip() for v in
               data["hints"] + data["forbidden_reveals"] + data["acceptable_solutions"])
    assert len(data["metadata"]["tags"]) >= 1
    assert data["metadata"]["difficulty"] in {"easy", "medium", "hard"}


@pytest.mark.parametrize("mid,data", all_cases())
def test_public_premise_and_hints_do_not_include_banned_spoilers(mid, data):
    public = [data["premise_public"], *data["hints"]]
    for word in data["forbidden_reveals"]:
        assert word == word.strip()
        assert word, mid
        for text in public:
            assert word.lower() not in text.lower(), (mid, word, text)
    assert not any(data["solution_summary"].casefold() in text.casefold() for text in public)


@pytest.mark.parametrize("mid,data", all_cases())
def test_solution_and_answer_variants_cover_core_facts(mid, data):
    # This is a sanity check against accidental empty content. It cannot
    # automatically validate semantic entailment: human review is mandatory.
    assert data["acceptable_solutions"][0].lower() != data["premise_public"].lower()
    assert len(set(data["acceptable_solutions"])) == len(data["acceptable_solutions"])
    assert all(len(s.strip()) >= 18 for s in data["acceptable_solutions"])


@pytest.mark.parametrize("mid,data", all_cases())
def test_every_case_plays_from_start_to_reveal(client, mid, data):
    created = client.post("/api/create_room", json={"mystery_id": mid})
    assert created.status_code == 200
    room = created.json()
    assert room["premise"] == data["premise_public"]
    assert room["title"] == data["title"]
    for number, hint in enumerate(data["hints"], 1):
        response = client.post("/api/hint", json={"room_id": room["room_id"], "text": "/hint"})
        assert response.status_code == 200
        assert response.json()["reply"] == f"Hint {number}: {hint}"
    assert client.post("/api/hint", json={
        "room_id": room["room_id"], "text": "/hint"
    }).json()["reply"] == "No more hints."
    answer = client.post("/api/reveal", json={"room_id": room["room_id"], "text": "/reveal"})
    assert answer.status_code == 200
    assert data["solution_summary"] in answer.json()["reply"]
    assert client.get(f"/api/join/{room['room_code']}").json()["solved"] is True


@pytest.mark.parametrize("mid,data", all_cases())
def test_offline_private_guess_accepts_exact_answer_variants(client, mid, data):
    # The deterministic offline fallback is lexical, not a real LLM judge.
    # Testing its exact authored solutions catches bad wiring between
    # content and the private-guess endpoint.
    room = client.post("/api/create_room", json={"mystery_id": mid}).json()
    answer = client.post("/api/private_guess", json={
        "room_id": room["room_id"], "guess": data["acceptable_solutions"][0]
    })
    assert answer.status_code == 200
    assert answer.json()["correct"] is True
    assert answer.json()["solved"] is True


def test_daily_rotation_has_twelve_different_consecutive_cases():
    catalog = [{"id": mid, "title": data["title"]} for mid, data in all_cases()]
    start = date(2026, 11, 1)
    selected = [
        challenge_for(start + timedelta(days=i), catalog)["mystery_id"]
        for i in range(13)
    ]
    assert len(set(selected[:12])) == 12
    assert selected[12] == selected[0]
