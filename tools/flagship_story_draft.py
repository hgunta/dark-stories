#!/usr/bin/env python3
"""Draft one mystery using a flagship model. No published story files are modified.

Run without --execute for a no-cost preflight. Actual paid work requires an
explicit budget, rates, and an API key in the environment.
"""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone


PROMPT = """You are the lead narrative designer of Dark Stories, a lateral-thinking
mystery game. Create ONE original mystery, not a list.

The entire experience must satisfy:
- Premise: 2–3 taut, vivid sentences, genuinely puzzling and literally true
  under the eventual answer. Don't misstate what witnesses saw.
- The reveal must be surprising, coherent and satisfying, with a human motive
  or compelling consequence and a causal chain that a player can discover.
- Avoid gadgets, technical failures, trivia, uncommon law, recordings, fish,
  a remote ferry, a late library book, a pianist in a blackout, doors and
  sensors, melodramatic conspiracies, and stock riddle remixes.
- Make the hidden mechanism distinguishable through at least 4 fair yes/no
  investigations; these should involve natural clues, not named specialist facts.
- Do not pad difficulty with unnecessary hidden facts or deny correct guesses.
- Prefer darkly playful, unsettling, or sharply ironic tone over sentimentality.

Use this format, plain UTF-8 text (no JSON):
TITLE:
PREMISE FOR PLAYERS:
SOLUTION FOR EDITORS:
THE CENTRAL MISTAKEN ASSUMPTION:
CAUSAL CHAIN (3+ numbered links):
TRUE YES/NO QUESTIONS (at least 6, with Yes answers):
FALSE YES/NO QUESTIONS (at least 3, with No answers):
FAIR ALTERNATIVE HYPOTHESES:
WHAT WOULD MAKE THIS STORY FAIL:
EDITORIAL SELF-CRITIQUE:

Think hard about physical plausibility and motivations. If the first idea is
obvious or implausible, discard it privately and develop a more satisfying one.
Don't claim human playtesting. Never approve your own story for production."""

CRITIC = """You are an adversarial editor of a lateral-thinking mystery game.
Review the complete unpublished draft supplied below. Be demanding and
specific. Identify logical contradictions, hidden arbitrary assumptions,
easy one-guess solves, accidental spoilers in the premise, weak player
incentives, tired tropes, and unnatural human behavior. For each risk,
quote the troublesome part of the draft and propose a concrete correction.
Score hook, twist, fairness, discovery, human interest, originality 0–5.
Recommend ACCEPT FOR HUMAN PLAYTEST, REWRITE, or REJECT.
Do not flatter the creator. Never add technical details just to force more
questions or suggest rejecting truthful guesses. Clearly distinguish
model evaluation from human playtesting."""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--writer", default="gpt-6-astra")
    p.add_argument("--critic", default="gpt-6.1-sol")
    p.add_argument("--max-cost-usd", type=float)
    p.add_argument("--writer-input-per-million", type=float)
    p.add_argument("--writer-output-per-million", type=float)
    p.add_argument("--critic-input-per-million", type=float)
    p.add_argument("--critic-output-per-million", type=float)
    p.add_argument("--output", type=Path, default=Path(".story-evals/flagship-draft.json"))
    a = p.parse_args()
    # Allow a generous output bound, one writer and one critic call.
    writer_tokens = 4800
    critic_tokens = 3000
    writer_input_bound = len(PROMPT.encode()) + 2000
    # Upper bound uses bytes of writer output as a conservative stand-in
    # for input tokens in the second pass, plus substantial overhead.
    critic_input_bound = len(CRITIC.encode()) + writer_tokens * 4 + 2000
    if a.execute:
        prices = [a.writer_input_per_million, a.writer_output_per_million,
                  a.critic_input_per_million, a.critic_output_per_million]
        if a.max_cost_usd is None or a.max_cost_usd <= 0 or any(v is None or v <= 0 for v in prices):
            p.error("--execute requires positive max cost and four verified price rates")
        if not os.environ.get("OPENAI_API_KEY"):
            p.error("OPENAI_API_KEY must be supplied securely in the environment")
        reservation = sum(x * y for x, y in zip(
            [writer_input_bound, writer_tokens, critic_input_bound, critic_tokens],
            prices)) / 1_000_000
        if reservation > a.max_cost_usd:
            p.error(f"Reserved estimate ${reservation:.2f} exceeds cap ${a.max_cost_usd:.2f}")
    else:
        print("DRY RUN; no API calls. Run with --execute and a budget to write one story.")
        return 0

    from openai import OpenAI
    client = OpenAI(timeout=240, max_retries=0)
    results = []
    try:
        for role, model, prompt, max_tokens, effort in [
            ("writer", a.writer, PROMPT, writer_tokens, "high"),
            ("critic", a.critic, CRITIC, critic_tokens, "medium"),
        ]:
            content = prompt if role == "writer" else (
                prompt + "\n\nCOMPLETE STORY DRAFT TO REVIEW:\n\n" + results[0]["text"])
            response = client.responses.create(
                model=model, input=content, reasoning={"effort": effort},
                max_output_tokens=max_tokens, store=False)
            text = response.output_text
            if not text or not text.strip():
                raise RuntimeError(f"{model} returned no user-visible text")
            results.append({
                "role": role, "model": model, "text": text,
                "input_tokens": getattr(response.usage, "input_tokens", None),
                "output_tokens": getattr(response.usage, "output_tokens", None),
            })
            # Private checkpoint after every successful paid model request.
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(json.dumps({
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "status": "unapproved draft", "results": results
            }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"{role} complete ({model}); draft is not approved.", flush=True)
    finally:
        if results:
            print(f"Completed {len(results)}/2 stages; checkpoint: {a.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
