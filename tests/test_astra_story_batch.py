"""Offline regression tests for the flagship story batch pipeline."""
from pathlib import Path
import importlib.util

module_file = Path(__file__).resolve().parents[1] / "tools" / "astra_story_batch.py"
spec = importlib.util.spec_from_file_location("astra_story_batch", module_file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_default_has_zero_api_calls(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert module.main(["--count", "6"]) == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_approved_budget_preflight(capsys):
    assert module.main(["--count", "6", "--max-cost-usd", "5"]) == 0
    assert "$2.490" in capsys.readouterr().out


def test_refuse_budget_below_reservation():
    import pytest
    with pytest.raises(SystemExit):
        module.main(["--count", "8", "--max-cost-usd", "1"])


def test_parse_critic_scores():
    text = ("HOOK: 4\nSURPRISE: 5\nLOGIC: 4\nFAIRNESS: 4\n"
            "STAKES: 5\nORIGINALITY: 3\nVERDICT: SHORTLIST\n")
    assert module.parse_review(text) == {
        "score": 25,
        "scores": {"HOOK": 4, "SURPRISE": 5, "LOGIC": 4,
                   "FAIRNESS": 4, "STAKES": 5, "ORIGINALITY": 3},
        "verdict": "SHORTLIST",
    }


def test_six_distinct_story_families():
    assert len({k for k, _ in module.TOPICS[:6]}) == 6
