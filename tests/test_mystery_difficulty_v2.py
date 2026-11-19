"""Content-only regression checks for the first difficulty-rewrite batch."""
import json
from pathlib import Path

import pytest

from backend.game import check_solution


ROOT = Path(__file__).resolve().parents[1] / "backend" / "mysteries"
REVISED = ("ms-006", "ms-008", "ms-009", "ms-011")


@pytest.mark.parametrize("mid", REVISED)
def test_rewritten_cases_require_several_distinct_causal_facts(mid):
    case = json.loads((ROOT / f"{mid}.json").read_text(encoding="utf-8"))
    facts = [fact["text"] for fact in case["facts"] if fact["required"]]
    assert len(facts) >= 4
    assert len(facts) == len(set(facts))
    assert len(case["hints"]) >= 2
    assert case["metadata"]["difficulty"] in {"medium", "hard"}


@pytest.mark.parametrize("mid,partial", [
    ("ms-006", "It was a book."),
    ("ms-006", "The library was closed."),
    ("ms-008", "A piano was playing."),
    ("ms-008", "The lights went out."),
    ("ms-009", "There was a ferry."),
    ("ms-009", "The ferry had no pilot."),
    ("ms-011", "The pump was on."),
    ("ms-011", "The water was calm."),
])
def test_obvious_fragments_are_not_complete_solutions_in_offline_fallback(mid, partial):
    case = json.loads((ROOT / f"{mid}.json").read_text(encoding="utf-8"))
    assert not check_solution(partial, case["acceptable_solutions"])


@pytest.mark.parametrize("mid", REVISED)
def test_acceptable_solutions_still_pass_offline_fallback(mid):
    case = json.loads((ROOT / f"{mid}.json").read_text(encoding="utf-8"))
    for solution in case["acceptable_solutions"]:
        assert check_solution(solution, case["acceptable_solutions"])
