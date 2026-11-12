"""Premise-first process must be non-publishing and safe by default."""
import importlib.util
from pathlib import Path

file=Path(__file__).resolve().parents[1]/"tools"/"premise_first_editorial.py"
spec=importlib.util.spec_from_file_location("premise_first_editorial",file)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_dry_run(capsys):
    assert module.main()==0
    out=capsys.readouterr().out
    assert "DRY RUN" in out
    assert "$2.15" in out

def test_parser_collects_premise_and_solution():
    raw="""=== IDEA 1 ===
TITLE: The Test
PREMISE: The door was shut. The room was empty.
SOLUTION: The room was occupied the previous night.
ASSUMPTION: Current time means all times.
FATAL_RISK: Generic.
=== IDEA 2 ===
TITLE: Second
PREMISE: Her bag was dry. The bridge was wet.
SOLUTION: She crossed earlier.
ASSUMPTION: Rain timing.
FATAL_RISK: Easy.
"""
    data=module.extract_ideas(raw)
    assert len(data)==2
    assert data[0]["title"]=="The Test"
    assert data[1]["solution"]=="She crossed earlier."

def test_scores_parse():
    answer="SURPRISE: 4\nINEVITABILITY: 5\nDISCOVERABILITY: 3\nTRUTH: 4\nPAYOFF: 4\nVERDICT: REWORK\n"
    assert module.parse_scores(answer)=={"score":20,"verdict":"REWORK"}
