"""Generated concepts are never published or charged for by default."""
import importlib.util
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "tools" / "generate_story_pitches.py"
spec = importlib.util.spec_from_file_location("generate_story_pitches", MODULE)
pitcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pitcher)


def test_generation_is_dry_run_by_default(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert pitcher.main(["--count", "24"]) == 0
    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert "4 batches" in output


def test_paid_run_without_prices_is_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "DUMMY")
    with pytest.raises(SystemExit):
        pitcher.main(["--count", "6", "--execute"])


def test_budget_reservation_grows_with_scope():
    a = pitcher.budget_reservation(
        count=6, max_output_tokens=4000, input_price=1, output_price=5)
    b = pitcher.budget_reservation(
        count=24, max_output_tokens=4000, input_price=1, output_price=5)
    assert 0 < a < b


def test_schema_contains_full_solution_but_not_automatic_publish():
    props = pitcher.IDEA["properties"]
    assert "public_premise" in props
    assert "full_solution" in props
    assert "mistaken_assumption" in props
    assert "discovery_questions" in props
    assert "weakness_to_investigate" in props
    source = MODULE.read_text()
    assert "git push" not in source
    assert "backend/mysteries/" not in source
