"""Capped paid evaluation of the Dark Stories moderation task.

NO network calls without --execute and OPENAI_API_KEY. Never used by production.
Only aggregate scores and case IDs are written to artifact, not private model text.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATES = {"gpt-4.1-mini": (.4, 1.6), "gpt-6-luna": (.1, .5),
         "gpt-6.1-terra": (1., 5.), "gpt-6.1-sol": (2., 10.)}
MAX_OUTPUT = 600
SCHEMA = {"type": "object", "properties": {"label": {
    "type": "string", "enum": ["Yes", "No", "Unknown", "Irrelevant", "AskYesNo", "Solved"]}},
    "required": ["label"], "additionalProperties": False}


def fixtures():
    rows = json.loads((ROOT / "evaluation/moderator_cases.json").read_text())["cases"]
    assert len(rows) >= 50 and len({r["id"] for r in rows}) == len(rows)
    assert {r["mystery_id"] for r in rows} == {"ms-001", "ms-002", "ms-003"}
    for r in rows:
        assert r["kind"] in {"question", "solution"}
        assert isinstance(r["question"], str) and r["question"]
        if r["kind"] == "question":
            assert r["expected"] in {"Yes", "No", "Unknown", "Irrelevant", "AskYesNo"}
        else:
            assert type(r["expected"]) is bool
    mysteries = {mid: json.loads((ROOT / "backend/mysteries" / (mid + ".json")).read_text())
                 for mid in {"ms-001", "ms-002", "ms-003"}}
    return rows, mysteries


def prompt(row, mystery):
    base = (
        "You are a lateral-thinking mystery moderator. Answer truthfully based on "
        "the PRIVATE facts. Judge semantic meaning, not exact word matches: if "
        "the victims are goldfish, 'are they fish?' is YES. A correct partial "
        "fact does not equal a full solution. Never invent or divulge facts.\n"
        "PUBLIC PREMISE: " + mystery["premise_public"] + "\n"
        "PRIVATE FACTS: " + json.dumps(mystery["facts"]) + "\n"
        "FULL SOLUTION: " + mystery["solution_summary"] + "\n"
        "ACCEPTABLE SOLUTIONS: " + json.dumps(mystery["acceptable_solutions"]) + "\n"
    )
    if row["kind"] == "question":
        base += ("TASK: Answer the YES/NO question only. Yes if true (even a broad "
                 "but correct category), No if false, AskYesNo if compound alternatives "
                 "need splitting, Unknown if private facts cannot decide, Irrelevant "
                 "only if off topic. Never reply Solved to questions. No nudges.")
    else:
        base += ("TASK: Judge a PRIVATE final explanation. Label Solved only when "
                 "the CORE CAUSAL MECHANISM is captured, not merely one true detail. "
                 "Accept equivalent wording, reject incomplete or incorrect explanations "
                 "with No. No hints or spoilers.")
    for h in row.get("history", []):
        base += "\nEarlier public chat (context, not ground truth): " + h["role"] + ": " + h["content"]
    return base


def reserve(model, system):
    inp, out = RATES[model]
    # Very conservative input bound; output bounded by max_output_tokens.
    return ((2 * len(system.encode("utf-8")) + 1024) * inp + MAX_OUTPUT * out) / 1_000_000


def actual_cost(model, usage):
    inp, out = RATES[model]
    # Ignore cached discounts to avoid understating costs.
    return (usage.input_tokens * inp + usage.output_tokens * out) / 1_000_000


def evaluate(rows, mysteries, models, budget):
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("No OPENAI_API_KEY configured; no paid calls made")
    from openai import OpenAI
    client = OpenAI(max_retries=0, timeout=40.0)
    start = time.monotonic()
    spent = 0.
    results = []
    for model in models:
        for row in rows:
            sys_prompt = prompt(row, mysteries[row["mystery_id"]])
            if spent + reserve(model, sys_prompt) > budget:
                print("Budget guard reached; stopping without another request.")
                return results, spent, time.monotonic() - start
            item = {"id": row["id"], "model": model, "kind": row["kind"],
                    "expected": row["expected"]}
            try:
                args = {
                    "model": model,
                    "input": [{"role": "system", "content": sys_prompt},
                              {"role": "user", "content": row["question"]}],
                    "max_output_tokens": MAX_OUTPUT,
                    "text": {"format": {"type": "json_schema", "name": "decision",
                                        "schema": SCHEMA, "strict": True}},
                    "store": False,
                }
                if model == "gpt-6-luna":
                    args["reasoning"] = {"effort": "none"}
                elif model.startswith("gpt-6"):
                    args["reasoning"] = {"effort": "low"}
                result = client.responses.create(**args)
                spent += actual_cost(model, result.usage)
                label = json.loads(result.output_text)["label"]
                predicted = (label == "Solved") if row["kind"] == "solution" else label
                item.update(status="ok", correct=predicted == row["expected"],
                            input_tokens=result.usage.input_tokens,
                            output_tokens=result.usage.output_tokens)
            except Exception as exc:
                # Do not log exception text (may contain proprietary API request data).
                item.update(status="error", error_type=type(exc).__name__, correct=False)
            results.append(item)
            if spent >= budget:
                print("Actual spend reached the configured budget; stopping.")
                return results, spent, time.monotonic() - start
    return results, spent, time.monotonic() - start


def aggregate(rows, results, models, spent, elapsed):
    summary = {"status": "incomplete", "spent_usd": round(spent, 6),
               "duration_seconds": round(elapsed, 1),
               "models": {}, "case_count": len(rows)}
    for model in models:
        matching = [r for r in results if r["model"] == model]
        ok = [r for r in matching if r["status"] == "ok"]
        def accuracy(kind):
            subset = [r for r in ok if r["kind"] == kind]
            return round(sum(r["correct"] for r in subset) / len(subset), 4) if subset else None
        summary["models"][model] = {
            "completed": len(ok), "errors": len(matching) - len(ok),
            "yes_no_accuracy": accuracy("question"),
            "final_solution_accuracy": accuracy("solution"),
            "input_tokens": sum(r.get("input_tokens", 0) for r in ok),
            "output_tokens": sum(r.get("output_tokens", 0) for r in ok),
            "incorrect_case_ids": [r["id"] for r in ok if not r["correct"]],
            "error_case_ids": [r["id"] for r in matching if r["status"] == "error"],
        }
    if all(summary["models"][m]["completed"] == len(rows) for m in models):
        summary["status"] = "complete"
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--budget-usd", type=float, default=5.0)
    parser.add_argument("--models", nargs="+", choices=RATES, default=list(RATES))
    parser.add_argument("--output", default="evaluation/results/summary.json")
    args = parser.parse_args()
    if not (0 < args.budget_usd <= 5.0):
        parser.error("Configured budget must be positive and no more than USD 5.")
    rows, mysteries = fixtures()
    reserved = sum(reserve(m, prompt(r, mysteries[r["mystery_id"]]))
                   for m in args.models for r in rows)
    print("Cases:", len(rows), "models:", args.models, "requests:", len(rows)*len(args.models),
          "preflight reserved USD:", round(reserved, 3),
          "configured spending cap USD:", args.budget_usd)
    if not args.execute:
        print("DRY RUN; zero API requests, no model scores.")
        return 0
    if reserved > args.budget_usd:
        print("Request count exceeds budget reservation. No requests made.")
        return 2
    try:
        results, spent, elapsed = evaluate(rows, mysteries, args.models, args.budget_usd)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    summary = aggregate(rows, results, args.models, spent, elapsed)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "complete" else 3


if __name__ == "__main__":
    sys.exit(main())
