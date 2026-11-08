"""Build a self-contained, offline mystery reviewer (no API keys or server).

Usage:
    python tools/build_mystery_review.py
    # Double-click mystery-review.html in the repository root.

The generated file contains secret solutions: keep it private. Never upload
or host it on the public game server. Review decisions are browser-local until
exported as JSON through the page.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "mysteries"
TEMPLATE = Path(__file__).with_name("mystery_review_template.html")
DEFAULT_OUTPUT = ROOT / "mystery-review.html"


def load_cases():
    cases = []
    for path in sorted(SOURCE.glob("ms-*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if case["mystery_id"] != path.stem:
            raise ValueError(f"mystery ID differs from filename: {path}")
        canonical = json.dumps(case, sort_keys=True, ensure_ascii=False).encode("utf-8")
        case["_review_fingerprint"] = hashlib.sha256(canonical).hexdigest()[:16]
        cases.append(case)
    if not cases:
        raise ValueError("No mysteries found")
    return cases


def generate(destination=DEFAULT_OUTPUT):
    # Escape the opening angle bracket so a story string containing </script>
    # cannot break out of the embedded JSON script element.
    data = json.dumps(load_cases(), ensure_ascii=False).replace("<", "\\u003c")
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count("__MYSTERY_DATA__") != 1:
        raise ValueError("Review template must contain one data placeholder")
    output = template.replace("__MYSTERY_DATA__", data)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a private offline mystery review desk")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="where to write the self-contained reviewer")
    args = parser.parse_args()
    output = generate(args.output)
    print(f"Generated {output} — open it in your browser. It contains spoilers; do not publish.")
