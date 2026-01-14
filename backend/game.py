import os, re, json, difflib
from pathlib import Path
from openai import OpenAI

MYSTERY_DIR = Path(__file__).resolve().parent / "mysteries"

def load_mystery(mid: str):
    with open(MYSTERY_DIR / f"{mid}.json", "r", encoding="utf-8") as f:
        return json.load(f)

def looks_like_hypothesis(text: str) -> bool:
    return bool(re.search(r"(because|therefore|so that|it was|i think|my guess|happened|explanation|cause)", text, re.I))

def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

def check_solution(user_text: str, acceptable: list[str]) -> bool:
    sims = [similarity(user_text, s) for s in acceptable]
    return max(sims) >= 0.72

def sanitize_output(s: str, forbidden: set[str]) -> str:
    low = s.lower()
    for w in forbidden:
        if w in low:
            return "Irrelevant"
    return s

def classify_question(user_text: str, system_prompt: str, client: OpenAI | None):
    """Return (label, nudge, fact_indices). If USE_API=false or no client, stub safely."""
    use_api = os.getenv("USE_API", "false").lower() == "true"
    if not use_api or client is None:
        # offline stub so you can test everything without API/quota
        return "Unknown", "(offline mode)", []

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
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
                            "enum": ["Yes", "No", "Irrelevant", "Unknown", "AskYesNo", "Solved"]
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

        return label, nudge, fact_indices

    return "Unknown", "", []

