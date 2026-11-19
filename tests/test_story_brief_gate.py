"""Deterministic preflight guards; not a substitute for literary judgment."""
import importlib.util
from pathlib import Path

p=Path(__file__).resolve().parents[1]/"tools"/"check_story_brief.py"
spec=importlib.util.spec_from_file_location("check_story_brief",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def example():
    return dict(
        working_title="Example",public_premise="Two facts seem incompatible.",
        causal_solution="A causes the event; B determines the outcome.",
        observed_evidence_a="Physical evidence in the premise",
        discovery_a="The physical evidence was initially misread",
        true_questions_a=["Was there a delay?","Was the object moved?"],
        observed_evidence_b="A separate human decision in the premise",
        discovery_b="The human action exploited the physical misconception",
        true_questions_b=["Did the person know?","Was it deliberate?"],
        causal_dependency="The second act is motivated by the first mechanism",
        first_guess_complete_solution="Likely shortcut guess",
        cheaper_alternative="Alternative interpretation",
        why_alternative_fails="Specific observed evidence rules it out",
        premise_truth_audit="All assertions literally true",
        human_payoff="An irony that follows rather than being bolted on",
        known_weakness="One part might still be obvious",
    )

def test_complete_brief_is_only_structurally_valid():
    assert m.validate(example())==[]

def test_reject_repeated_discovery():
    data=example()
    data["discovery_b"]=data["discovery_a"]
    assert any("Same discovery" in x for x in m.validate(data))

def test_reject_reused_observation():
    data=example()
    data["observed_evidence_b"]=data["observed_evidence_a"]
    assert any("separate observational anchors" in x for x in m.validate(data))

def test_reject_missing_question_paths():
    data=example()
    data["true_questions_a"]=["Does this matter?"]
    assert any("at least two" in x for x in m.validate(data))

def test_auto_approved_flag_never_passes():
    data=example()
    data["editorial_status"]="approved"
    assert any("No automatic approval" in x for x in m.validate(data))
