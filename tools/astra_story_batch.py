#!/usr/bin/env python3
"""Six distinct one-at-a-time Astra drafts + independent Sol critiques.

Zero API calls by default. With --execute, this spends at most the *estimated*
conservative output/input-token reservation given by --max-cost-usd. Actual
invoice varies with pricing, caching, and provider conditions. Never publishes
or modifies mystery JSON. Results stay in .story-evals/ and are not committed.

Uses background Responses + polling to avoid HTTP read timeouts on GPT-6 Astra.
Each request is independently checkpointed to disk. A failed candidate never
triggers a paid automatic retry.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

OUTDIR = Path(".story-evals")
TOPICS = [
    ("misleading_evidence", "Physical evidence looks definitive, but its chronology has been misunderstood; a human act creates the apparent impossibility."),
    ("deliberate_choice", "A seemingly monstrous or irrational decision has a surprising, coherent hidden motive with a dark or ironic consequence."),
    ("misinterpreted_witness", "Two honest witnesses appear incompatible because their assumptions about the scene or identity are subtly wrong."),
    ("timing", "An event's observed sequence is true, yet a compelling hidden timing relationship completely changes its meaning."),
    ("role_identity", "A person's role or relationship has been misread in a way that changes the whole story, without twins, costumes or legal loopholes."),
    ("ordinary_object", "An ordinary non-electronic object or everyday action gets misinterpreted, leading to a striking but logical outcome."),
    ("spatial", "A misleading physical arrangement or viewpoint has a fair reveal and real human stakes."),
    ("dark_karma", "An attempt to avoid an unpleasant consequence instead causes an ironic and memorable outcome; all causal links are fair."),
]
WRITER = """You are a demanding master designer of ORIGINAL lateral-thinking mysteries in the spirit of classic Dark Stories.
Your job is to craft ONE outstanding mystery, not a bundle of ideas or a technical factoid.

The exact story family is: {family}. Creative challenge: {brief}

QUALITY BAR:
- Public premise: 2–3 short sentences with a *compelling* concrete contradiction and human stakes. No vague "something seemed strange".
- Every public assertion is literally true under the final solution. No wordplay on "died" unless it is extremely fair.
- The explanation must be surprising, psychologically interesting, and retrospectively inevitable.
- Have at least THREE natural causal inferences. The story must not collapse after guessing one gadget/noun.
- A first-time player can discover those links by honest YES/NO questions with ordinary knowledge.
- Avoid specialist law/technology, recordings, electronic systems, remote control, sensors, maintenance, fake paintings, e-books, clocks, wedding ceremonies, suicide twists, revenge killings, unlikely conspiracies, real-world criminal instruction, and stock riddles.
- Do not invent convenient hidden characters or equipment just to plug logic holes.
- The story should have an emotionally compelling, darkly ironic, or startling payoff, NOT merely a sweet anecdote.
- Someone should be able to narrate the answer in one short satisfying paragraph after play.
- This is not a contest to make players ask arbitrarily many questions. Correct partial deductions deserve Yes.

Previous weak mysteries include flash showing smoke, e-book checkout, prerecorded piano, remote ferry, skis, broken pool pump, and temperature sticker. Avoid all of those.
PRE-RELEASE SELF TEST: Imagine a skeptic tries 3 obvious guesses after reading the premise. If those solve it, discard internally and design a different concept. Then verify every event in the chronology.

Respond in the following plain-text, clearly labeled form. Do NOT use JSON or markdown code fences.
TITLE:
PUBLIC PREMISE:
FULL SOLUTION:
KEY MISTAKEN ASSUMPTION:
THREE-STEP CAUSAL EXPLANATION:
YES QUESTIONS (five diverse examples):
NO QUESTIONS (three diverse examples):
PLAUSIBLE WRONG PATHS (two):
LITERAL-TRUTH CHECK:
WHY THE REVEAL IS FUN:
MOST SERIOUS WEAKNESS:
"""
CRITIC = """You are an adversarial puzzle editor of dark, lateral-thinking mysteries. You have NEVER met the writer.
Evaluate the candidate as if it were competing for one of only three publication slots.
For each of the six criteria rate integer 0–5: Hook, Surprise, Logic, Fairness of Discovery, Human Stakes, Originality.
Reject contrived backstories, hidden assumptions, impossible chronology, routine explanations, lucky one-question guesses and twists requiring special knowledge.
Give TWO concrete first-guess attempts from the PUBLIC PREMISE alone (simulate a blind reader; do not let the provided answer contaminate these attempts). Then analyze whether any guesses already completely solve the case.
Explicitly check every sentence of premise against the solution's literal truth.
Return an unflattering useful critique, 0–30 total, and REJECT/REWORK/SHORTLIST verdict. Only SHORTLIST if >=24/30, no score <3, no major logic loopholes.
Respond with exactly these labeled lines followed by a short critique paragraph:
HOOK: <0-5>
SURPRISE: <0-5>
LOGIC: <0-5>
FAIRNESS: <0-5>
STAKES: <0-5>
ORIGINALITY: <0-5>
VERDICT: <REJECT|REWORK|SHORTLIST>
BLIND FIRST GUESSES:
PREMISE TRUTH AUDIT:
FAILURES:
IMPROVEMENTS:
"""

def call_background(model, prompt, max_tokens, effort, *, poll_seconds, cap_seconds):
    from openai import OpenAI
    cli = OpenAI(timeout=45, max_retries=0)
    response = cli.responses.create(
        model=model, input=prompt, background=True,
        reasoning={"effort": effort}, max_output_tokens=max_tokens,
        store=False,
    )
    deadline = time.monotonic() + cap_seconds
    while response.status in ("queued", "in_progress"):
        if time.monotonic() >= deadline:
            # Do NOT start another paid call. The queued response may still
            # consume tokens; its preconfigured output cap limits exposure.
            return {"status": "timeout", "response_id": response.id, "text": "",
                    "input_tokens": 0, "output_tokens": max_tokens}
        time.sleep(poll_seconds)
        response = cli.responses.retrieve(response.id)
    usage = getattr(response, "usage", None)
    return {
        "status": response.status,
        "response_id": response.id,
        "text": response.output_text or "",
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "error": str(response.error) if response.error else None,
    }


def save(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def collect_candidates(outpath, model, topics, *, worker_count, poll_seconds, cap_seconds):
    existing = {}
    if outpath.is_file():
        existing = json.loads(outpath.read_text(encoding="utf-8")).get("candidates", {})
    def worker(entry):
        family, brief = entry
        return family, call_background(model, WRITER.format(family=family, brief=brief),
                                       9500, "low", poll_seconds=poll_seconds,
                                       cap_seconds=cap_seconds)
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(worker, entry) for entry in topics
                   if entry[0] not in existing]
        for f in as_completed(futures):
            family, result = f.result()
            existing[family] = result
            save({"candidates": existing}, outpath)
            print(f"WRITER {family}: {result['status']}, chars={len(result['text'])}, "
                  f"input={result['input_tokens']}, output={result['output_tokens']}", flush=True)
    return existing


def collect_critiques(outpath, model, candidates, *, worker_count, poll_seconds, cap_seconds):
    data = json.loads(outpath.read_text(encoding="utf-8"))
    critiques = data.get("critiques", {})
    def worker(item):
        family, story = item
        return family, call_background(model, CRITIC + "\n\nCANDIDATE:\n" + story["text"],
                                       3000, "medium", poll_seconds=poll_seconds,
                                       cap_seconds=cap_seconds)
    pending = [(key, val) for key, val in candidates.items()
               if val["status"] == "completed" and val["text"].strip() and key not in critiques]
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for f in as_completed([pool.submit(worker, item) for item in pending]):
            family, result = f.result()
            critiques[family] = result
            save({"candidates": candidates, "critiques": critiques}, outpath)
            print(f"CRITIC {family}: {result['status']}, chars={len(result['text'])}, "
                  f"input={result['input_tokens']}, output={result['output_tokens']}", flush=True)
    return critiques


def parse_review(text):
    scores = {}
    for key in ("HOOK", "SURPRISE", "LOGIC", "FAIRNESS", "STAKES", "ORIGINALITY"):
        match = re.search(r"^" + key + r":\s*([0-5])(?:\b|/5)", text, flags=re.M)
        if not match:
            return {"score": None, "verdict": "UNPARSEABLE"}
        scores[key] = int(match.group(1))
    m = re.search(r"^VERDICT:\s*(REJECT|REWORK|SHORTLIST)", text, flags=re.M)
    return {"score": sum(scores.values()), "scores": scores,
            "verdict": m.group(1) if m else "UNPARSEABLE"}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--count", type=int, default=6)
    p.add_argument("--max-cost-usd", type=float, default=3.70)
    p.add_argument("--prior-estimated-usd", type=float, default=0)
    p.add_argument("--total-budget-usd", type=float, default=5)
    p.add_argument("--output", type=Path, default=OUTDIR / "astra-six.json")
    p.add_argument("--worker-count", type=int, default=3)
    p.add_argument("--poll-seconds", type=float, default=4)
    p.add_argument("--cap-seconds", type=float, default=600)
    a = p.parse_args(argv)
    if not 5 <= a.count <= 8 or not 1 <= a.worker_count <= 4:
        p.error("count must be 5–8, worker count 1–4")
    if a.poll_seconds < 2 or a.cap_seconds < 60:
        p.error("Invalid poll/cap parameters")
    # Conservative cost reservation for short Astra prompts and up to
    # 9500 tokens (including hidden reasoning) per story. Critic receives
    # no more than 12k input tokens incl. story text and system prompt.
    # Standard pricing: Astra $10/$50, Sol $2/$10 per million tokens.
    upper = a.count * ((4000*10+9500*50)+(12000*2+3000*10))/1_000_000
    print(f"Additional reserved estimate ${upper:.3f}; prior estimate "
          f"${a.prior_estimated_usd:.3f}; approved total ${a.total_budget_usd:.2f}.")
    if (upper > a.max_cost_usd or a.max_cost_usd <= 0 or
        a.prior_estimated_usd < 0 or
        a.prior_estimated_usd + upper > a.total_budget_usd):
        p.error("Conservative reservation exceeds approved cap")
    if not a.execute:
        print("DRY RUN; no paid calls.")
        return 0
    if not os.environ.get("OPENAI_API_KEY"):
        p.error("OPENAI_API_KEY not set")
    topics = TOPICS[:a.count]
    candidates = collect_candidates(a.output, "gpt-6-astra", topics,
                                    worker_count=a.worker_count,
                                    poll_seconds=a.poll_seconds,
                                    cap_seconds=a.cap_seconds)
    critiques = collect_critiques(a.output, "gpt-6.1-sol", candidates,
                                 worker_count=a.worker_count,
                                 poll_seconds=a.poll_seconds,
                                 cap_seconds=a.cap_seconds)
    ranked = []
    for family, item in candidates.items():
        if not item.get("text"):
            continue
        critique = critiques.get(family, {})
        review = parse_review(critique.get("text", ""))
        ranked.append({"family": family, **review,
                       "title": re.search(r"^TITLE:\s*(.+)", item["text"], flags=re.M).group(1)
                       if re.search(r"^TITLE:\s*(.+)", item["text"], flags=re.M) else family})
    ranked.sort(key=lambda x: (x.get("score") or -1), reverse=True)
    existing = json.loads(a.output.read_text(encoding="utf-8"))
    existing.update({"ranked": ranked, "budget_reservation_usd": upper,
                     "completed_at": datetime.now(timezone.utc).isoformat()})
    save(existing, a.output)
    print("RESULTS " + json.dumps(ranked, ensure_ascii=False))
    print("ALL REPORTS ARE UNAPPROVED; DO NOT MERGE OR DEPLOY")
    if len(ranked) < 3:
        raise RuntimeError(f"Only {len(ranked)} usable stories; need at least 3 to shortlist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
