"""Launch the local, spoiler-containing mystery review desk in one step.

Run from any working directory:
    python tools/review_mysteries.py
Or double-click review-mysteries.command / review-mysteries.bat.

This rebuilds from *all current* ms-*.json files every time, then opens
the review HTML in the default browser. No server, API key, or dependencies.
"""
import argparse
from pathlib import Path
import sys
import webbrowser

# Work both as 'python tools/review_mysteries.py' and via OS shortcut.
from build_mystery_review import generate, load_cases


def main(argv=None):
    parser = argparse.ArgumentParser(description="Refresh and open the private Dark Stories puzzle reviewer")
    parser.add_argument("--no-open", action="store_true", help="Rebuild without opening a browser")
    args = parser.parse_args(argv)
    cases = load_cases()  # fail fast for malformed new puzzle files
    destination = generate()
    print(f"Review desk updated: {len(cases)} mysteries.", flush=True)
    print(f"File: {destination}", flush=True)
    print("Private spoiler content. Do not publish this file.", flush=True)
    if not args.no_open:
        if not webbrowser.open(destination.resolve().as_uri()):
            print("Your browser did not open automatically. Open the HTML file above.", flush=True)
    return destination


if __name__ == "__main__":
    main()
