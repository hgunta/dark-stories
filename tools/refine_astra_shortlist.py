#!/usr/bin/env python3
"""One budgeted Astra revision of top 3 stories plus independent Sol re-review.

Reads the *completed* five-story report downloaded from the prior GitHub
Actions artifact. No secrets or mystery JSON committed. No automatic retries.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path

from astra_story_batch import call_background, parse_review, save, CRITIC

EDITOR = """You are the senior writer of Dark Stories, a lateral-thinking game.
An independently generated mystery and its uncompromising editorial review
are provided below. Perform ONE serious revision that attempts to solve the
critic's specific problems. If the central premise is fundamentally defective,
REPLACE the premise and plot rather than adding arbitrary complexity.
Requirements:
- A concise, unforgettable 2- or 3-sentence premise, all clauses literally true.
- A coherent causal chain, non-obvious but discoverable without niche knowledge.
- A surprising and satisfying human/darkly ironic payoff, not generic equipment.
- 4+ genuinely varied routes of Yes/No investigation.
- Every event and person's motive explained plausibly.
- NEVER use extra hidden facts simply to force a player to ask more questions.
- Any confident first-guess full explanation must be treated as an earned solve.
- Prioritize delight and logical rigor over making the story excessively dark.

Return plain text with headings and no JSON:
TITLE:
PUBLIC PREMISE:
FULL SOLUTION:
MISTAKEN ASSUMPTION:
DISCOVERABLE TRUE QUESTIONS (at least five):
PLAUSIBLE FALSE QUESTIONS:
KEY CAUSAL CHAIN:
LITERAL TRUTH OF EACH PREMISE SENTENCE:
HOW THIS REVISION ANSWERS THE CRITIC:
REMAINING HONEST WEAKNESS:

ORIGINAL CANDIDATE:
{original}

INDEPENDENT CRITIC REVIEW:
{critique}
"""

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path(".story-evals/refined-three.json"))
    p.add_argument("--execute", action="store_true")
    p.add_argument("--max-cost-usd", type=float, default=2.7)
    p.add_argument("--prior-spend-estimate", type=float, default=2.26)
    p.add_argument("--total-budget-usd", type=float, default=5)
    a=p.parse_args()
    # Astra 6500 output / 3000 input, Sol 2500 output / 12000 input.
    reservation=3*((3000*10+6500*50)+(12000*2+2500*10))/1_000_000
    print(f"Preflight: current reserved ${reservation:.3f}; prior estimated "
          f"${a.prior_spend_estimate:.3f}; total maximum ${a.total_budget_usd:.2f}", flush=True)
    if (a.max_cost_usd < reservation or
        a.prior_spend_estimate + reservation > a.total_budget_usd):
        p.error("Cumulative reservation exceeds approved budget")
    if not a.execute:
        print("DRY RUN. No API calls.")
        return 0

    src=json.loads(a.source.read_text(encoding="utf-8"))
    shortlist=src.get("ranked", [])[:3]
    if len(shortlist)!=3:
        raise RuntimeError("Previous batch did not have 3 successful critic reviews")

    output={"selected":shortlist,"revisions":{},"reviews":{}}
    def revise(entry):
        family=entry["family"]
        story=src["candidates"][family]["text"]
        critique=src["critiques"][family]["text"]
        return family, call_background(
            "gpt-6-astra", EDITOR.format(original=story, critique=critique),
            6500, "low", poll_seconds=4, cap_seconds=600)
    with ThreadPoolExecutor(max_workers=3) as executor:
        fs=[executor.submit(revise, entry) for entry in shortlist]
        for f in as_completed(fs):
            family, result=f.result()
            output["revisions"][family]=result
            save(output,a.output)
            print(f"REVISION {family}: {result['status']}, {len(result['text'])} chars, "
                  f"{result['input_tokens']} input tokens, {result['output_tokens']} output tokens",
                  flush=True)

    def critique(pair):
        family, result=pair
        return family, call_background(
            "gpt-6.1-sol", CRITIC + "\n\nREVISED CANDIDATE:\n"+result["text"],
            2500,"medium",poll_seconds=4,cap_seconds=600)
    good=[(key,val) for key,val in output["revisions"].items()
          if val["status"]=="completed" and val["text"].strip()]
    with ThreadPoolExecutor(max_workers=3) as executor:
        for f in as_completed([executor.submit(critique,pair) for pair in good]):
            family, result=f.result()
            output["reviews"][family]=result
            save(output,a.output)
            print(f"REREVIEW {family}: {result['status']}, "
                  f"{result['input_tokens']} input, {result['output_tokens']} output tokens",flush=True)
    results=[]
    for family, val in output["revisions"].items():
        review=output["reviews"].get(family,{})
        parsed=parse_review(review.get("text",""))
        results.append({"family":family,"revision_status":val["status"],
                        "review_status":review.get("status"),**parsed})
    results.sort(key=lambda x:x.get("score") or -1,reverse=True)
    output["ranked"]=results
    output["reserved_this_run_usd"]=reservation
    output["finished_at"]=datetime.now(timezone.utc).isoformat()
    save(output,a.output)
    print("REREVIEW_RANKINGS "+json.dumps(results,ensure_ascii=False),flush=True)
    if len(good)<3: raise RuntimeError("Fewer than three completed revised stories")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
