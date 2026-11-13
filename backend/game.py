import os, re, json, difflib
from pathlib import Path
from openai import OpenAI

MYSTERY_DIR = Path(__file__).resolve().parent / "mysteries"
EXPERIMENTAL_DIR = Path(__file__).resolve().parent / "experimental_mysteries"
EXPERIMENTAL_IDS = frozenset({"ex-001", "ex-002"})

def load_mystery(mid: str):
    # Preview-only cases are explicitly allowlisted and stored apart from the
    # main library; they never enter /api/mysteries or the featured rotation.
    folder = EXPERIMENTAL_DIR if mid in EXPERIMENTAL_IDS else MYSTERY_DIR
    with open(folder / f"{mid}.json", "r", encoding="utf-8") as f:
        return json.load(f)

def looks_like_complete_theory_attempt(text: str) -> bool:
    """Route plausible explanations to a semantic judge, never score by words.

    Short declarative theories count: neither word count nor keywords are
    prerequisites for solving. Plain Yes/No questions normally use the
    question moderator; question-form *causal* theories get the solve check.
    """
    cleaned = " ".join(text.strip().split())
    if len(cleaned) < 18 or cleaned.lower().startswith("/"):
        return False
    interrogative = re.match(
        r"^(is|are|was|were|did|does|do|could|would|has|have|should|"
        r"can|will|why|how|where|what|when|who)\b", cleaned, re.I
    )
    if interrogative:
        return bool(re.search(
            r"\b(because|therefore|hence|which meant|which means|so|"
            r"as soon as|as a result|meaning that|resulting in|"
            r"but|yet|failed to|didn't|did not)\b",
            cleaned, re.I
        ))
    return True

def looks_like_hypothesis(text: str) -> bool:
    return bool(re.search(r"(because|therefore|so that|it was|i think|my guess|happened|explanation|cause)", text, re.I))

def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

def check_solution(user_text: str, acceptable: list[str]) -> bool:
    sims = [similarity(user_text, s) for s in acceptable]
    return max(sims) >= 0.72

def direct_yes_fact_question(user_text: str, mystery: dict):
    """Answer only explicitly authored, exact-meaning identity questions.

    This supplements (not replaces) semantic moderation. It prevents false
    negatives on core synonyms without exposing the hidden answer or relying
    on keyword substring matching: 'not fish?' and multi-part questions never
    match. Each authored alias points to a true, indexed mystery fact.
    """
    question = re.sub(r"\\s+", " ", user_text.strip().lower().rstrip("?.!")).strip()
    if not question:
        return None
    subjects = ("it", "they", "the victims", "the couple", "the deceased", "the two")
    starters = ("is", "are", "was", "were")
    for group in mystery.get("direct_yes_facts", []):
        index = group.get("fact_index")
        if type(index) is not int or not (0 <= index < len(mystery.get("facts", []))):
            continue
        fact = mystery["facts"][index]
        if isinstance(fact, dict) and fact.get("truth") is False:
            continue
        for phrase in group.get("phrases", []):
            if not isinstance(phrase, str) or not phrase.strip():
                continue
            candidate = re.sub(r"\\s+", " ", phrase.strip().lower())
            if any(question == f"{starter} {subject} {candidate}"
                   for starter in starters for subject in subjects):
                return "Yes", [index]
    return None


def sanitize_output(s: str, forbidden: set[str]) -> str:
    low = s.lower()
    for w in forbidden:
        if w in low:
            return "Irrelevant"
    return s

def _observe_origin(observer, origin):
    if observer is not None:
        try:
            observer(origin)
        except Exception:
            pass  # Optional instrumentation must not affect classification.


def classify_question(user_text: str, system_prompt: str, client: OpenAI | None, *, observe_origin=None):
    """Return (label, nudge, fact_indices). If USE_API=false or no client, stub safely."""
    use_api = os.getenv("USE_API", "false").lower() == "true"
    if not use_api or client is None:
        # offline stub so you can test everything without API/quota
        _observe_origin(observe_origin, "offline_stub")
        return "Unknown", "(offline mode)", []

    model = os.getenv("DARK_STORIES_MODERATOR_MODEL", "gpt-4.1-mini")
    if model == "gpt-6-luna":
        # Use the same Responses API and JSON-schema output used in evaluation.
        schema = {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["question", "hypothesis", "command"]},
                "label": {"type": "string", "enum": [
                    "Yes", "No", "Irrelevant", "Unknown", "AskYesNo", "AlmostSolved", "Solved"
                ]},
                "short_explanation": {"type": "string"},
                "fact_indices": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["kind", "label", "short_explanation", "fact_indices"],
            "additionalProperties": False,
        }
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            reasoning={"effort": "none"},
            max_output_tokens=600,
            text={"format": {"type": "json_schema", "name": "moderator_decide",
                             "schema": schema, "strict": True}},
            store=False,
            timeout=30,
        )
        args = json.loads(response.output_text)
        label = args.get("label", "Unknown")
        nudge = (args.get("short_explanation") or "").strip()
        indices = args.get("fact_indices") or []
        indices = [i for i in indices if type(i) is int] if isinstance(indices, list) else []
        _observe_origin(observe_origin, "ai_tool")
        return label, nudge, indices

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": "moderator_decide",
                "description": "Label input and produce minimal response.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["question", "hypothesis", "command"]},
                        "label": {
                            "type": "string",
                            "enum": ["Yes", "No", "Irrelevant", "Unknown", "AskYesNo", "AlmostSolved", "Solved"]
                        },
                        "short_explanation": {
                            "type": "string",
                            "description": "Optional <=10-word nudge with no spoilers.",
                            "maxLength": 80
                        },
                        "fact_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Indices of private facts directly tested by the user's question."
                        }
                    },
                    "required": ["kind", "label"]
                }
            }
        }],
        temperature=0.2,
        timeout=30
    )

    msg = resp.choices[0].message
    if getattr(msg, "tool_calls", None):
        import json as _json
        args = _json.loads(msg.tool_calls[0].function.arguments)

        label = args.get("label", "Unknown")
        nudge = (args.get("short_explanation") or "").strip()
        fact_indices = args.get("fact_indices") or []

        # Defensive: ensure fact_indices is a list[int]
        if not isinstance(fact_indices, list):
            fact_indices = []
        fact_indices = [i for i in fact_indices if isinstance(i, int)]

        _observe_origin(observe_origin, "ai_tool")
        return label, nudge, fact_indices

    _observe_origin(observe_origin, "ai_fallback")
    return "Unknown", "", []

