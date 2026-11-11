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
    "Produce sharply varied concepts across unrelated mechanism types. "
    "Every premise sentence must remain literally TRUE under the solution; "
    "do not smuggle in false eyewitness claims or retroactively invent key details. "
    "Each story needs a concrete compelling contradiction, 2–3 natural causal "
    "links, a distinctive reinterpretation, and a reveal that feels earned. "
    "An unlikely but heartwarming anecdote is not automatically a mystery. "
    "If the first obvious question resolves everything, do not propose it. "
    "Avoid weddings, funerals, clerical mistakes, surprise parties, and "
    "unexplained criminal conspiracies as shortcuts. "
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


def budget_reservation(*, count, max_output_tokens, input_price, output_price, batch_size=CONCEPTS_PER_BATCH):
    """Conservative estimate, not a billing guarantee or currency quotation."""
    batches = math.ceil(count / batch_size)
    # Reserve enough input space for instructions and prior-idea titles.
    input_token_budget = batches * (len((SYSTEM + AVOID).encode("utf-8")) + 10000)
    output_token_budget = batches * max_output_tokens
    return (input_token_budget * input_price +
            output_token_budget * output_price) / 1_000_000


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=24,
                        help="Requested pitch count (1–30)")
    parser.add_argument("--batch-size", type=int, choices=(1, 3, 6), default=6,
                        help="Smaller batches improve reliability for premium models")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--execute", action="store_true",
                        help="Required for any paid API call")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--input-price-per-million", type=float)
    parser.add_argument("--output-price-per-million", type=float)
    parser.add_argument("--output", type=Path, default=Path(".story-evals/pitches.json"))
    parser.add_argument("--max-output-tokens", type=int, default=4000)
    args = parser.parse_args(argv)
    if not 1 <= args.count <= 30 or args.count % args.batch_size:
        parser.error("--count must be 1–30 and divisible by --batch-size")
    if not 1500 <= args.max_output_tokens <= 6000:
        parser.error("--max-output-tokens must be 1500–6000")
    print(f"Plan: {args.count} story concepts in {args.count // args.batch_size} batches.")
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
                                input_price=rates[0], output_price=rates[1],
                                batch_size=args.batch_size)
    print(f"Reserved estimated maximum ${budget:.4f}; actual invoice may differ.")
    if budget > args.max_cost_usd:
        parser.error("Potential spend exceeds the specified cap")
    from openai import OpenAI
    client = OpenAI(timeout=180, max_retries=0)
    seen = set()
    pitches = []
    for batch in range(args.count // args.batch_size):
        user = (AVOID + "\nAlready proposed titles (do not repeat): " +
                json.dumps([x["title"] for x in pitches]) +
                f"\nCreate exactly {args.batch_size} meaningfully different mystery pitches.")
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
        try:
            ideas = json.loads(response.output_text)["ideas"]
        except (json.JSONDecodeError, KeyError) as exc:
            # Preserve the partial draft privately for debugging; don't
            # silently turn malformed output into a playable mystery.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            partial = args.output.parent / f"failed-pitch-batch-{batch + 1}.txt"
            partial.write_text(response.output_text, encoding="utf-8")
            raise RuntimeError(
                f"Batch {batch + 1} returned incomplete/invalid JSON. "
                f"Partial draft saved to {partial}; no automatic retry."
            ) from exc
        if len(ideas) != args.batch_size:
            raise ValueError(f"Batch {batch + 1} returned {len(ideas)} ideas, expected {args.batch_size}")
        for idea in ideas:
            title = idea["title"].casefold()
            if title in seen:
                raise ValueError(f"Duplicate concept title: {idea['title']}")
            seen.add(title)
            pitches.append(idea)
        # Checkpoint each completed batch so a later failure doesn't destroy
        # previous successful paid calls. These are private drafts, not game JSON.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = args.output.parent / "pitch-checkpoint.json"
        checkpoint.write_text(json.dumps(pitches, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
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
