#!/usr/bin/env python3
"""Opt-in story pitch generation. Does not edit playable mysteries.

Example (replace the sample prices with the provider's CURRENT rates):
  python tools/generate_story_pitches.py --execute --count 24 \
    --max-cost-usd 2 --input-price-per-million 0.5 \
    --output-price-per-million 2
Dry-run is the default. All ideas must be screened and human-playtested.
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONCEPTS_PER_BATCH = 6
SYSTEM = (
    "You are a literary editor commissioning genuinely enjoyable Dark Stories "
    "lateral-thinking mysteries. Avoid generic technical failures, obscure "
    "equipment, trivia, semantic loopholes, forced ambiguity, gore, and "
    "well-known riddle clones. Make a reader genuinely curious. Each premise "
    "is a vivid two-sentence paradox. The solution is surprising but follows "
    "from coherent ordinary-life causality and a mistaken assumption. "
    "The player can reach the explanation by asking honest yes/no questions. "
    "Build human motive, stakes or dark comedy where appropriate. Do not "
    "manufacture difficulty through hidden arbitrary conditions. "
    "Produce six DIVERSE concepts per batch across unrelated mechanism types. "
    "Do not output generic approval or filler."
)
AVOID = (
    "Existing/retired concepts: fish in broken bowl; short man pressing lift "
    "button with umbrella; parachute not opening; smoke revealed in camera "
    "flash; forged painting with thick frame; electronic book borrowed; "
    "arriving on skis; prerecorded concert; remote-operated ferry; automatic "
    "greenhouse vents; pool pump failure; medication temperature sticker. "
    "Do not use sensor calibration, backup power, AI glitches, a recording "
    "that fools people, obvious vehicle automation, or specialist science."
)
IDEA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "public_premise": {"type": "string"},
        "full_solution": {"type": "string"},
        "mistaken_assumption": {"type": "string"},
        "discovery_questions": {"type": "array", "items": {"type": "string"}},
        "mechanism_family": {"type": "string"},
        "weakness_to_investigate": {"type": "string"},
    },
    "required": [
        "title", "public_premise", "full_solution", "mistaken_assumption",
        "discovery_questions", "mechanism_family", "weakness_to_investigate"
    ],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {"ideas": {"type": "array", "items": IDEA}},
    "required": ["ideas"],
    "additionalProperties": False,
}


def budget_reservation(*, count, max_output_tokens, input_price, output_price):
    """Conservative estimate, not a billing guarantee or currency quotation."""
    batches = math.ceil(count / CONCEPTS_PER_BATCH)
    # Reserve enough input space for instructions and prior-idea titles.
    input_token_budget = batches * (len((SYSTEM + AVOID).encode("utf-8")) + 10000)
    output_token_budget = batches * max_output_tokens
    return (input_token_budget * input_price +
            output_token_budget * output_price) / 1_000_000


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=24,
                        help="Requested pitch count (6–30, generated in batches of six)")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--execute", action="store_true",
                        help="Required for any paid API call")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--input-price-per-million", type=float)
    parser.add_argument("--output-price-per-million", type=float)
    parser.add_argument("--output", type=Path, default=Path(".story-evals/pitches.json"))
    parser.add_argument("--max-output-tokens", type=int, default=4000)
    args = parser.parse_args(argv)
    if not 6 <= args.count <= 30 or args.count % CONCEPTS_PER_BATCH:
        parser.error("--count must be a multiple of six between 6 and 30")
    if not 1500 <= args.max_output_tokens <= 6000:
        parser.error("--max-output-tokens must be 1500–6000")
    print(f"Plan: {args.count} story concepts in {args.count // 6} batches.")
    if not args.execute:
        print("DRY RUN — no tokens spent, no stories published.")
        return 0
    rates = (args.input_price_per_million, args.output_price_per_million)
    if (args.max_cost_usd is None or args.max_cost_usd <= 0 or
        any(r is None or r <= 0 for r in rates)):
        parser.error("Paid execution requires a positive cap and both model prices")
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY must be set securely for paid execution")
    budget = budget_reservation(count=args.count,
                                max_output_tokens=args.max_output_tokens,
                                input_price=rates[0], output_price=rates[1])
    print(f"Reserved estimated maximum ${budget:.4f}; actual invoice may differ.")
    if budget > args.max_cost_usd:
        parser.error("Potential spend exceeds the specified cap")
    from openai import OpenAI
    client = OpenAI(timeout=90, max_retries=0)
    seen = set()
    pitches = []
    for batch in range(args.count // 6):
        user = (AVOID + "\nAlready proposed titles (do not repeat): " +
                json.dumps([x["title"] for x in pitches]) +
                "\nCreate exactly 6 meaningfully different mystery pitches.")
        response = client.responses.create(
            model=args.model,
            input=[{"role": "system", "content": SYSTEM},
                   {"role": "user", "content": user}],
            max_output_tokens=args.max_output_tokens,
            reasoning={"effort": "low"},
            store=False,
            text={"format": {"type": "json_schema", "name": "pitch_batch",
                             "schema": SCHEMA, "strict": True}},
        )
        if not response.output_text:
            raise RuntimeError(f"Batch {batch + 1} returned no usable content")
        ideas = json.loads(response.output_text)["ideas"]
        if len(ideas) != CONCEPTS_PER_BATCH:
            raise ValueError(f"Batch {batch + 1} returned {len(ideas)} ideas, expected 6")
        for idea in ideas:
            title = idea["title"].casefold()
            if title in seen:
                raise ValueError(f"Duplicate concept title: {idea['title']}")
            seen.add(title)
            pitches.append(idea)
        print(f"Drafted {len(pitches)} ideas; NONE approved yet.", flush=True)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "note": "Unreviewed AI pitch ideas. Not game content. Human approval required.",
        "estimated_budget_reservation_usd": round(budget, 6),
        "supplied_prices_per_million": {
            "input": rates[0], "output": rates[1]
        },
        "pitches": pitches,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(pitches)} unreviewed ideas to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
