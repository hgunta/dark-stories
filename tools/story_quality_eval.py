#!/usr/bin/env python3
"""Opt-in paid editorial SCREENING for Dark Stories, not an automatic publisher.

Default: print a dry-run plan with ZERO API calls.
Run from repository root:
  python tools/story_quality_eval.py --ids ms-006 ms-008 --execute \
      --max-cost-usd 2.00 --input-price-per-million 0.50 \
      --output-price-per-million 2.00

Those sample prices are NOT pricing claims. Supply CURRENT prices for the
selected model from the provider. Require human review and blind playtests.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "backend" / "mysteries"

DIMENSIONS = (
    "hook", "twist", "fairness", "questioning", "human_interest", "originality"
)
BLIND_SCHEMA = {
    "type": "object",
    "properties": {
        "first_guess_mechanisms": {"type": "array", "items": {"type": "string"}},
        "yes_no_questions": {"type": "array", "items": {"type": "string"}},
        "one_step_risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "blind_comment": {"type": "string"},
    },
    "required": ["first_guess_mechanisms", "yes_no_questions", "one_step_risk", "blind_comment"],
    "additionalProperties": False,
}
CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "integer"},
        "twist": {"type": "integer"},
        "fairness": {"type": "integer"},
        "questioning": {"type": "integer"},
        "human_interest": {"type": "integer"},
        "originality": {"type": "integer"},
        "fatal_flaws": {"type": "array", "items": {"type": "string"}},
        "minimal_solve": {"type": "string"},
        "recommendation": {"type": "string", "enum": ["retire", "rewrite", "hold", "candidate"]},
        "editorial_note": {"type": "string"},
    },
    "required": [*DIMENSIONS, "fatal_flaws", "minimal_solve", "recommendation", "editorial_note"],
    "additionalProperties": False,
}
SYSTEM_BLIND = (
    "Act as an experienced but UNBRIEFED lateral-thinking-mystery player. "
    "You see ONLY the public premise. Produce up to 3 plausible first guesses "
    "of the central mechanism, then 5 specific yes/no questions. "
    "Do not fabricate a canonical solution. Flag if the premise seems trivial. "
    "Do not claim to be an actual human playtester."
)
SYSTEM_CRITIC = (
    "Act as a demanding independent mystery editor, not a helpful reviewer. "
    "Critique whether this is an entertaining, fair lateral-thinking story. "
    "Score each dimension 0 through 5. Reward surprising, retrospectively "
    "inevitable human stories. Penalize one-word answers, generic equipment "
    "failures, specialist knowledge, arbitrary facts, boring stakes, and "
    "premises that directly leak the answer. Report the minimal plausible solve. "
    "Never suggest the game should reject a truthful partial guess."
)


def load_cases(ids, directory=CATALOG):
    cases = []
    for mid in ids:
        if not mid.startswith("ms-") or not mid[3:].isdigit():
            raise ValueError(f"Invalid mystery ID: {mid}")
        path = directory / f"{mid}.json"
        case = json.loads(path.read_text(encoding="utf-8"))
        if case["mystery_id"] != mid:
            raise ValueError(f"ID mismatch for {mid}")
        cases.append(case)
    return cases


def jobs_for(cases):
    jobs = []
    for case in cases:
        mid = case["mystery_id"]
        # The first call is genuinely BLIND: neither the solution nor private
        # facts are included in the model prompt.
        premise = json.dumps({
            "title": case["title"], "premise": case["premise_public"]
        }, ensure_ascii=False)
        full = json.dumps(case, ensure_ascii=False)
        jobs.append((mid, "blind", SYSTEM_BLIND, premise, BLIND_SCHEMA))
        jobs.append((mid, "critic", SYSTEM_CRITIC, full, CRITIC_SCHEMA))
    return jobs


def maximum_reserved_cost(jobs, *, max_output_tokens, input_price, output_price):
    # UTF-8 byte count + 2,000 tokens/request generously reserves space for
    # tokenization & message overhead. This is an estimate, NOT a billing cap.
    # Reasoning models may count reasoning tokens against max_output_tokens.
    input_bound = sum(len((system + user).encode("utf-8")) + 2000
                      for _, _, system, user, _ in jobs)
    output_bound = len(jobs) * max_output_tokens
    return (input_bound * input_price + output_bound * output_price) / 1_000_000


def summarize(review):
    if not review or review.get("error"):
        return None
    scores = [review.get(dim) for dim in DIMENSIONS]
    if not all(type(v) is int and 0 <= v <= 5 for v in scores):
        raise ValueError("Out-of-range editorial scores")
    return {"total": sum(scores), "passes_automated_score_gate":
            sum(scores) >= 24 and min(scores) >= 3 and not review["fatal_flaws"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--execute", action="store_true",
                        help="Authorize paid OpenAI calls; absent by default")
    parser.add_argument("--max-cost-usd", type=float, default=None,
                        help="Required with --execute; estimated upper bound")
    parser.add_argument("--input-price-per-million", type=float, default=None,
                        help="Required with --execute; check current provider pricing")
    parser.add_argument("--output-price-per-million", type=float, default=None,
                        help="Required with --execute; check current provider pricing")
    parser.add_argument("--max-output-tokens", type=int, default=850)
    parser.add_argument("--output", type=Path, default=Path(".story-evals/latest.json"))
    parser.add_argument("--catalog", type=Path, default=CATALOG,
                        help="Alternative directory containing candidate JSON files")
    args = parser.parse_args(argv)
    if args.max_output_tokens < 250 or args.max_output_tokens > 1500:
        parser.error("max-output-tokens must be between 250 and 1500")
    cases = load_cases(args.ids, args.catalog)
    jobs = jobs_for(cases)
    print(f"Plan: {len(cases)} mysteries, {len(jobs)} model calls, model={args.model}.")
    if not args.execute:
        print("DRY RUN — no API calls, no changes to mysteries or deployment.")
        print("Provide --execute and budget/prices to run paid editorial screening.")
        return 0

    rates = (args.input_price_per_million, args.output_price_per_million)
    if (args.max_cost_usd is None or args.max_cost_usd <= 0 or
        any(v is None or v <= 0 for v in rates)):
        parser.error("--execute requires positive --max-cost-usd and both model prices")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required for --execute (never commit it)")
    reserved = maximum_reserved_cost(
        jobs, max_output_tokens=args.max_output_tokens,
        input_price=rates[0], output_price=rates[1])
    print(f"Estimated worst-case reservation: ${reserved:.4f} "
          f"(configured prices; actual invoice may differ).")
    if reserved > args.max_cost_usd:
        parser.error("Estimated reservation exceeds budget; reduce scope before running")

    from openai import OpenAI
    client = OpenAI(timeout=40, max_retries=0)
    results = []
    for mid, role, system, prompt, schema in jobs:
        print(f"Evaluating {mid} — {role}", flush=True)
        response = client.responses.create(
            model=args.model,
            input=[{"role": "system", "content": system},
                   {"role": "user", "content": prompt}],
            max_output_tokens=args.max_output_tokens,
            reasoning={"effort": "low"},
            store=False,
            text={"format": {"type": "json_schema", "name": "editorial_review",
                             "schema": schema, "strict": True}},
        )
        if not response.output_text:
            raise RuntimeError(f"No parseable response for {mid}/{role}; stop.")
        verdict = json.loads(response.output_text)
        if role == "critic":
            verdict["score_summary"] = summarize(verdict)
        results.append({
            "mystery_id": mid, "role": role, "verdict": verdict,
            "input_tokens": getattr(response.usage, "input_tokens", None),
            "output_tokens": getattr(response.usage, "output_tokens", None),
        })
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model, "cases": args.ids,
        "estimated_maximum_usd": round(reserved, 6),
        "rates_supplied_by_operator": {"input_per_million": rates[0],
                                      "output_per_million": rates[1]},
        "note": "AI screening only. Spoiler-bearing output; no human results.",
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"Saved editorial report to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
