"""Paid editorial screener: no network during ordinary tests or dry-runs."""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "story_quality_eval.py"
spec = importlib.util.spec_from_file_location("story_quality_eval", MODULE)
editorial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(editorial)


def test_no_paid_calls_in_dry_run(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert editorial.main(["--ids", "ms-006", "ms-008"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "4 model calls" in out


def test_blind_player_prompts_cannot_see_private_solution():
    case = editorial.load_cases(["ms-006"])[0]
    jobs = editorial.jobs_for([case])
    blind = jobs[0]
    critic = jobs[1]
    assert blind[1] == "blind" and critic[1] == "critic"
    assert case["solution_summary"] not in blind[3]
    assert case["solution_summary"] in critic[3]
    assert case["acceptable_solutions"][0] not in blind[3]


def test_default_cost_estimate_is_positive_but_requires_budget():
    jobs = editorial.jobs_for(editorial.load_cases(["ms-006"]))
    reserved = editorial.maximum_reserved_cost(
        jobs, max_output_tokens=850, input_price=1.0, output_price=5.0)
    assert 0 < reserved < 1


def test_reject_invalid_id():
    with pytest.raises(ValueError):
        editorial.load_cases(["../../../.env"])


def test_reject_paid_run_without_budget(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "FAKE_NO_CALL")
    with pytest.raises(SystemExit):
        editorial.main(["--ids", "ms-006", "--execute"])


def test_high_and_low_score_rubric():
    passing = {key: 4 for key in editorial.DIMENSIONS}
    passing["fatal_flaws"] = []
    assert editorial.summarize(passing)["passes_automated_score_gate"]
    passing["fatal_flaws"] = ["Arbitrary secret rule"]
    assert not editorial.summarize(passing)["passes_automated_score_gate"]
