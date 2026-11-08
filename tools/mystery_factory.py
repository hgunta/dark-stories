"""Mystery Factory: bounded writer / skeptical verifier / simulated-player pipeline.

Candidate outputs are written ONLY to private-review candidates/, NEVER to the
served mystery catalog. API runs are opt-in and capped at twelve model calls.
No model-produced code is executed; model output is parsed as untrusted JSON.

Run:
  python tools/mystery_factory.py --dry-run
  python tools/mystery_factory.py --run-id example --api  # costs OpenAI tokens
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "backend" / "mysteries"
OUTPUT_ROOT = ROOT / "candidates"
MODEL = "gpt-4.1-mini"
MAX_CALLS = 12
ALLOWED_LABELS = {"Yes", "No", "Unknown", "Irrelevant", "AskYesNo", "Solved"}
THEMES = ["observation", "ordinary technology", "physical evidence", "mistaken assumptions",
          "a mundane coincidence", "a subtle environmental mechanism"]


class FactoryError(Exception):
    pass


def read_catalog():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CATALOG.glob("ms-*.json"))]


def validate_case(case, existing):
    """Mandatory objective checks; independent human editorial review still required."""
    if not isinstance(case, dict):
        return ["Mystery must be a JSON object."]
    keys = {"mystery_id", "title", "premise_public", "solution_summary",
            "facts", "forbidden_reveals", "acceptable_solutions", "hints", "metadata"}
    errors = [] if set(case) == keys else ["Schema keys do not match the game content format."]
    for k in ("mystery_id", "title", "premise_public", "solution_summary"):
        if not isinstance(case.get(k), str) or not case[k].strip():
            errors.append(f"{k}: non-empty string required.")
    if errors:
        return errors
    if not re.fullmatch(r"ms-\d{3}", case["mystery_id"]):
        errors.append("ID must use ms-XXX.")
    if len(case["premise_public"]) < 40 or len(case["solution_summary"]) < 50:
        errors.append("Premise (40+) and solution (50+) need meaningful length.")
    existing_ids = {c["mystery_id"] for c in existing}
    if case["mystery_id"] in existing_ids:
        errors.append("Case ID collides with published library.")
    if case["title"].casefold() in {c["title"].casefold() for c in existing}:
        errors.append("Title duplicates a published case.")
    facts = case.get("facts")
    if not isinstance(facts, list) or len(facts) < 3 or any(
        not isinstance(f, dict) or set(f) != {"text", "required"}
        or not isinstance(f["text"], str) or not f["text"].strip()
        or not isinstance(f["required"], bool) for f in facts
    ):
        errors.append("Facts must be 3+ {text, required} objects.")
    elif sum(f["required"] for f in facts) < 3:
        errors.append("At least three facts must be required.")
    for name, minimum in (("hints", 2), ("acceptable_solutions", 3), ("forbidden_reveals", 3)):
        vals = case.get(name)
        if not isinstance(vals, list) or len(vals) < minimum or any(
            not isinstance(v, str) or not v.strip() for v in vals
        ):
            errors.append(f"{name} must contain {minimum}+ nonempty strings.")
    meta = case.get("metadata")
    if (not isinstance(meta, dict)
        or meta.get("difficulty") not in {"easy", "medium", "hard"}
        or not isinstance(meta.get("tags"), list)
        or not meta["tags"]
        or not all(isinstance(t, str) and t for t in meta["tags"])):
        errors.append("Metadata requires valid difficulty and tags.")
    if all(isinstance(case.get(k), list) for k in ("hints", "forbidden_reveals")):
        for term in case["forbidden_reveals"]:
            for snippet in [case["premise_public"], *case["hints"]]:
                if isinstance(term, str) and term and term.casefold() in snippet.casefold():
                    errors.append(f"Forbidden spoiler '{term}' appears in public text.")
    return errors


class LLM:
    def __init__(self, client, model=MODEL, max_calls=MAX_CALLS):
        self.client, self.model, self.max_calls, self.calls = client, model, max_calls, 0

    def json(self, role, request):
        if self.calls >= self.max_calls:
            raise FactoryError("Model-call ceiling reached")
        self.calls += 1  # count failed calls toward the budget, too
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": role}, {"role": "user", "content": request}],
            response_format={"type": "json_object"},
            temperature=0.3,
            timeout=30,
        )
        try:
            data = json.loads(response.choices[0].message.content)
        except (ValueError, AttributeError, IndexError, TypeError) as exc:
            raise FactoryError("Invalid model JSON response") from exc
        if not isinstance(data, dict):
            raise FactoryError("Model result must be a JSON object")
        return data


WRITER_ROLE = """You are the Dark Stories Writer. Produce one original, fair, logically
deducible lateral-thinking mystery (no graphic violence, no real person, no harmful
instructions). The premise should create one striking puzzle but not reveal its
answer. Avoid overused fishbowl, elevator umbrella, parachute and other library
twists. Return ONLY a JSON object matching exactly:
mystery_id (provided ID), title, premise_public, solution_summary,
facts [{text,required:boolean}], forbidden_reveals [strings],
acceptable_solutions [at least three diverse paraphrases], hints [exactly two],
metadata {difficulty: easy|medium|hard, tags: [strings]}.
At least three facts must be required. Ensure a consistent physical/causal
explanation; do not depend on arbitrary unmentioned events. Hints must not
contain any forbidden reveal word. The twist must be fair from yes/no questions.
This is a draft for skeptical review, not an approved case."""

VERIFIER_ROLE = """You are an adversarial *independent* Dark Stories verifier.
Do not try to be agreeable with the writer. Your job is to find logical gaps,
unsupported assumptions, duplicate twists, premature spoilers, ambiguous
answers, unfair scoring and incorrect solution adjudication.
Simulate a first-time player attempting to solve the case. Propose exactly
three Yes/No probe questions with labels Yes/No/Unknown and one wrong
near-miss solution. Supply reasoning about what a moderator MUST answer.
Return JSON: {"recommendation":"revise"|"review", "issues":[{"severity":
"high"|"medium"|"low","description":"...","suggested_fix":"..."}],
"probes":[{"question":"...","expected":"Yes"|"No"|"Unknown",
"reason":"..."}], "wrong_guess":"...", "plausibility_notes":"..."}.
Never treat your opinion as objective proof. Flag anything you cannot verify."""

PROBE_ROLE = """You are a separate, strict yes/no mystery moderator being
probed by an adversarial verifier. Return JSON {"label":"Yes"|"No"|"Unknown"
|"Irrelevant"|"AskYesNo"|"Solved"}. If the case does not establish a fact,
say Unknown rather than inventing details. Do not reveal the solution or any
spoiler words in the label. For a normal yes/no question, do not say Solved. For a solution-guess probe, label Solved only if the guess really explains all essential facts; otherwise No."""


def next_id(existing):
    used = [int(c["mystery_id"][3:]) for c in existing
            if re.fullmatch(r"ms-\d{3}", c.get("mystery_id", ""))]
    return f"ms-{max(used, default=0) + 1:03d}"


def assess(llm, case, existing):
    packet = {"draft": case, "existing_titles_and_solutions": [
        {"title": x["title"], "solution_summary": x["solution_summary"]}
        for x in existing
    ]}
    review = llm.json(VERIFIER_ROLE, json.dumps(packet))
    issues = review.get("issues")
    probes = review.get("probes")
    if not isinstance(issues, list) or not isinstance(probes, list) or len(probes) != 3:
        raise FactoryError("Verifier returned malformed issues or probe list")
    checks = []
    for p in probes:
        if not isinstance(p, dict) or p.get("expected") not in {"Yes", "No", "Unknown"} or not isinstance(p.get("question"), str):
            raise FactoryError("Invalid verifier probe")
        # Independent probe model calls use the same moderation-shaped task,
        # but are not equivalent to exercising the production HTTP game.
        response = llm.json(PROBE_ROLE, json.dumps({"case": case, "question": p["question"]}))
        actual = response.get("label")
        if actual not in ALLOWED_LABELS:
            raise FactoryError("Invalid probe answer")
        checks.append({"question": p["question"], "expected": p["expected"],
                       "actual": actual, "match": actual == p["expected"],
                       "reason": p.get("reason", "")})
    wrong = review.get("wrong_guess")
    if not isinstance(wrong, str) or not wrong.strip():
        raise FactoryError("Verifier must provide a wrong near-miss guess")
    wrong_response = llm.json(PROBE_ROLE, json.dumps({
        "case": case, "question": wrong, "submission_type": "private_solution_guess"
    }))
    wrong_label = wrong_response.get("label")
    if wrong_label not in ALLOWED_LABELS:
        raise FactoryError("Invalid near-miss probe answer")
    return {"verifier": review, "probe_checks": checks,
            "near_miss_check": {"wrong_guess": wrong, "actual": wrong_label,
                                "pass": wrong_label != "Solved"}}


def run_factory(llm, existing, identifier, topic):
    titles = [{"title": x["title"], "solution_summary": x["solution_summary"]} for x in existing]
    case = llm.json(WRITER_ROLE, json.dumps({
        "assigned_id": identifier, "theme": topic, "avoid_similar_to": titles,
    }))
    validation = validate_case(case, existing)
    reviews = []
    if not validation:
        reviews.append(assess(llm, case, existing))
    # One revision maximum and no unbounded agent debate. If the first draft
    # is structurally wrong, obtain feedback from deterministic validation.
    needs_revision = bool(validation) or (
        bool(reviews) and (reviews[-1]["verifier"].get("recommendation") == "revise"
                           or any(not p["match"] for p in reviews[-1]["probe_checks"])
                           or not reviews[-1]["near_miss_check"]["pass"])
    )
    if needs_revision and llm.calls <= llm.max_calls - 6:
        feedback = {"schema_errors": validation, "verifier": reviews[-1] if reviews else None}
        revised = llm.json(WRITER_ROLE, json.dumps({
            "assigned_id": identifier, "theme": topic, "previous_draft": case,
            "required_revisions": feedback, "avoid_similar_to": titles,
        }))
        case = revised
        validation = validate_case(case, existing)
        if not validation:
            reviews.append(assess(llm, case, existing))
    passing = (
        not validation and bool(reviews)
        and reviews[-1]["verifier"].get("recommendation") == "review"
        and not any(i.get("severity") == "high" for i in reviews[-1]["verifier"]["issues"] if isinstance(i, dict))
        and all(p["match"] for p in reviews[-1]["probe_checks"])
        and reviews[-1]["near_miss_check"]["pass"]
    )
    # "ready_for_human_review" is not "approved"; no promotion to published library.
    return case, {"status": "ready_for_human_review" if passing else "needs_revision",
                  "schema_issues": validation, "verification_rounds": reviews,
                  "model_calls": llm.calls, "max_model_calls": llm.max_calls,
                  "human_approval_required": True,
                  "production_moderator_tested": False}


def save_candidate(candidate, report, output, run_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", run_id):
        raise FactoryError("Invalid run ID")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{run_id}.json"
    report_path = output / f"{run_id}.report.json"
    if path.exists() or report_path.exists():
        raise FactoryError("Refusing to overwrite prior candidate or review")
    path.write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path, report_path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", action="store_true", help="Opt in to paid OpenAI calls")
    parser.add_argument("--dry-run", action="store_true", help="Print plan; no model calls")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--topic", default=None)
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args(argv)
    existing = read_catalog()
    identifier = next_id(existing)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    topic = args.topic or THEMES[datetime.now(timezone.utc).timetuple().tm_yday % len(THEMES)]
    if args.dry_run or not args.api:
        print(json.dumps({"mode": "dry-run", "assigned_id": identifier,
                          "theme": topic, "existing_cases": len(existing),
                          "max_model_calls": MAX_CALLS,
                          "publishes": False}, indent=2))
        return 0
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for --api. No keys are stored.")
    from openai import OpenAI
    llm = LLM(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))
    candidate, report = run_factory(llm, existing, identifier, topic)
    path, report_path = save_candidate(candidate, report, args.output, run_id)
    print(f"Wrote PRIVATE draft: {path}")
    print(f"Wrote verification report: {report_path}")
    print(f"Status: {report['status']}; model calls: {report['model_calls']}/{MAX_CALLS}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
