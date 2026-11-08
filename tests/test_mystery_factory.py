"""Offline, zero-network tests for the opt-in two-role mystery factory."""
import copy
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import mystery_factory as factory

ROOT = Path(__file__).resolve().parents[1]


def sample():
    case = json.loads((ROOT / "backend" / "mysteries" / "ms-012.json").read_text())
    case["mystery_id"] = "ms-013"
    case["title"] = "The Blue Sticker"
    return case


def verifier(recommendation="review", wrong="It was stolen"):
    return {"recommendation": recommendation, "issues": [],
            "probes": [
                {"question": "Was it wet?", "expected": "No", "reason": "Packaging dry"},
                {"question": "Was it medication?", "expected": "Yes", "reason": "The contents"},
                {"question": "Was it Tuesday?", "expected": "Unknown", "reason": "Date not specified"},
            ], "wrong_guess": wrong, "plausibility_notes": "A test candidate only."}


class FakeLLM:
    def __init__(self, answers):
        self.answers = iter(copy.deepcopy(answers))
        self.calls = 0
        self.max_calls = 12

    def json(self, role, request):
        self.calls += 1
        assert self.calls <= 12
        return next(self.answers)


def test_schema_and_spoiler_failures_are_reported():
    case = sample()
    assert factory.validate_case(case, factory.read_catalog()) == []
    case["hints"][0] = "It's refrigerated medication"
    case["title"] = "The Dead Couple"
    errors = factory.validate_case(case, factory.read_catalog())
    assert any("Forbidden spoiler" in x for x in errors)
    assert any("duplicates" in x for x in errors)


def test_independent_verifier_and_simulated_player_probes():
    answers = [sample(), verifier(), {"label": "No"}, {"label": "Yes"},
               {"label": "Unknown"}, {"label": "No"}]
    llm = FakeLLM(answers)
    case, report = factory.run_factory(llm, factory.read_catalog(), "ms-013", "observation")
    assert case["mystery_id"] == "ms-013"
    assert report["status"] == "ready_for_human_review"
    assert report["human_approval_required"] is True
    assert report["production_moderator_tested"] is False
    assert report["model_calls"] == 6
    assert all(check["match"] for check in report["verification_rounds"][0]["probe_checks"])
    assert report["verification_rounds"][0]["near_miss_check"]["pass"] is True


def test_bad_verifier_feedback_triggers_one_revision_and_retest():
    first = sample()
    first["hints"][0] = "It's refrigerated medicine"
    revised = sample()
    review = verifier()
    answers = [first, revised, review, {"label": "No"},
               {"label": "Yes"}, {"label": "Unknown"}, {"label": "No"}]
    llm = FakeLLM(answers)
    case, report = factory.run_factory(llm, factory.read_catalog(), "ms-013", "observation")
    assert case == revised
    assert report["status"] == "ready_for_human_review"
    assert report["model_calls"] == 7


def test_bad_probe_triggers_revision_and_second_full_verification():
    first = sample()
    revised = sample()
    revised["title"] = "The Violet Sticker"
    answers = [first, verifier(), {"label": "Yes"}, {"label": "Yes"},
               {"label": "Unknown"}, {"label": "Solved"},
               revised, verifier(), {"label": "No"}, {"label": "Yes"},
               {"label": "Unknown"}, {"label": "No"}]
    llm = FakeLLM(answers)
    case, report = factory.run_factory(llm, factory.read_catalog(), "ms-013", "observation")
    assert case["title"] == "The Violet Sticker"
    assert report["status"] == "ready_for_human_review"
    assert report["model_calls"] == 12
    assert len(report["verification_rounds"]) == 2


def test_model_budget_prevents_unbounded_calls():
    responses = [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=json.dumps({"hello": "world"})
    ))])]
    class Completions:
        def create(self, **kwargs):
            return responses[0]
    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    llm = factory.LLM(client, max_calls=2)
    for _ in range(2):
        assert llm.json("role", "question") == {"hello": "world"}
    with pytest.raises(factory.FactoryError, match="ceiling"):
        llm.json("role", "question")
    assert llm.calls == 2


def test_dry_run_needs_no_openai_key_and_writes_nothing(tmp_path):
    p = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "mystery_factory.py"), "--dry-run",
         "--output", str(tmp_path / "drafts")],
        capture_output=True, text=True, check=True
    )
    data = json.loads(p.stdout)
    assert data["publishes"] is False
    assert data["max_model_calls"] == 12
    assert not list(tmp_path.iterdir())


def test_output_never_overwrites_and_is_separate_from_game_catalog(tmp_path):
    case = sample()
    report = {"status": "needs_revision", "human_approval_required": True}
    path, report_path = factory.save_candidate(case, report, tmp_path / "candidates", "test-001")
    assert path.exists() and report_path.exists()
    assert path.parent != factory.CATALOG
    with pytest.raises(factory.FactoryError, match="overwrite"):
        factory.save_candidate(case, report, path.parent, "test-001")
    for bad in ("../foo", "a/b", "", "hello world"):
        with pytest.raises(factory.FactoryError, match="Invalid run ID"):
            factory.save_candidate(case, report, path.parent, bad)


def test_scheduled_workflow_is_opt_in_not_production_publish():
    workflow = (ROOT / ".github" / "workflows" / "mystery-factory.yml").read_text()
    assert "cron:" in workflow
    assert "ENABLE_MYSTERY_FACTORY == 'true'" in workflow
    assert "execute != true" in workflow
    assert "OPENAI_API_KEY" in workflow
    assert "gh pr create --draft" in workflow
    assert "candidates/" in workflow
    assert 'git add "candidates/' in workflow
    assert 'git add "backend/mysteries/' not in workflow
