"""Local owner-only structured feedback report. No HTTP endpoint, no raw records."""
import argparse
import json
from pathlib import Path

from .feedback_storage import SQLiteFeedbackStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read local feedback aggregates only")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--prune-expired", action="store_true",
                        help="Explicitly remove rows older than 30 days before reporting")
    args = parser.parse_args(argv)
    store = SQLiteFeedbackStore(args.database)
    if args.prune_expired:
        removed = store.delete_expired()
        print(f"Removed {removed} expired feedback entries", flush=True)
    print(json.dumps(store.summarize(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
