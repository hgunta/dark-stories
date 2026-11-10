"""The benchmark can be validated without API access or paid calls."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "evaluation" / "moderator_cases.json"


def test_hand_labeled_fixture_is_diverse_and_no_unreviewed_mysteries():
    entries = json.loads(DATA.read_text())["cases"]
    assert len(entries) == 61
    assert len({row["id"] for row in entries}) == len(entries)
    assert {r["mystery_id"] for r in entries} == {"ms-001", "ms-002", "ms-003"}
    assert {r["kind"] for r in entries} == {"question", "solution"}
    refs = {r["id"]: r for r in entries}
    assert refs["fish_2"]["expected"] == "Yes"
    assert refs["fish_gold"]["expected"] == "Yes"
    assert refs["fish_partial"]["expected"] is False
    assert refs["fish_full"]["expected"] is True


def test_benchmark_dry_run_never_requires_api_key():
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "evaluation/run_moderator_eval.py")],
        capture_output=True, text=True, timeout=10, cwd=ROOT, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "requests: 244" in result.stdout


def test_execute_without_key_is_rejected_before_network():
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "evaluation/run_moderator_eval.py"),
         "--execute", "--budget-usd", "5"],
        capture_output=True, text=True, timeout=10, cwd=ROOT, env=env,
    )
    assert result.returncode == 2, result.stderr
    assert "no paid calls made" in result.stdout.lower()


def test_budget_over_five_dollars_is_rejected():
    result = subprocess.run(
        [sys.executable, str(ROOT / "evaluation/run_moderator_eval.py"),
         "--execute", "--budget-usd", "6"],
        capture_output=True, text=True, timeout=10, cwd=ROOT,
    )
    assert result.returncode != 0
    assert "no more than USD 5" in result.stderr
