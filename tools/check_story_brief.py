#!/usr/bin/env python3
"""Structural preflight for *unapproved* two-revelation story pitches.

This intentionally does NOT claim to judge creativity or puzzle fairness.
It rejects incomplete editorial briefs *before* any paid drafting. Human and
independent blind-model critique remain required for semantic approval.

Usage:
  python tools/check_story_brief.py path/to/candidate.json
No external API calls; never modifies playable mysteries.
"""
import argparse
import json
from pathlib import Path

REQUIRED = (
    "working_title", "public_premise", "causal_solution",
    "observed_evidence_a", "discovery_a", "true_questions_a",
    "observed_evidence_b", "discovery_b", "true_questions_b",
    "causal_dependency", "first_guess_complete_solution",
    "cheaper_alternative", "why_alternative_fails",
    "premise_truth_audit", "human_payoff", "known_weakness"
)

def validate(candidate):
    errors=[]
    for name in REQUIRED:
        value=candidate.get(name)
        if value is None or value=="" or value==[]:
            errors.append(f"Missing meaningful field: {name}")
    for name in ("true_questions_a","true_questions_b"):
        v=candidate.get(name)
        if not isinstance(v,list) or len(v)<2 or not all(
            isinstance(x,str) and x.strip().endswith("?") for x in v):
            errors.append(f"{name} needs at least two question strings")
    for name in ("public_premise","causal_solution","discovery_a","discovery_b",
                 "observed_evidence_a","observed_evidence_b","causal_dependency"):
        if not isinstance(candidate.get(name),str):
            errors.append(f"{name} must be text")
    if candidate.get("discovery_a")==candidate.get("discovery_b"):
        errors.append("Same discovery repeated in both slots")
    if candidate.get("observed_evidence_a")==candidate.get("observed_evidence_b"):
        errors.append("Both deductions must have separate observational anchors")
    if candidate.get("editorial_status")=="approved":
        errors.append("No automatic approval: only editorial/human review can approve")
    return sorted(set(errors))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidate",type=Path)
    a=p.parse_args(argv)
    data=json.loads(a.candidate.read_text(encoding="utf-8"))
    errors=validate(data)
    if errors:
        for e in errors:print("REJECT:",e)
        return 1
    print("STRUCTURAL CHECK ONLY: complete brief; still needs blind and human critique.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
