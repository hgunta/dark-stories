"""Explicit local launcher to test SQLite-backed player feedback, never production startup."""
import argparse
from pathlib import Path
import sys

from .feedback_storage import SQLiteFeedbackStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only feedback persistence preview")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port out of range")
    store = SQLiteFeedbackStore(args.database)
    store.initialize()
    # Existing backend/app.py uses top-level imports for the documented Uvicorn entrypoint.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import app as game
    game.feedback_store = store
    import uvicorn
    uvicorn.run(game.app, host="127.0.0.1", port=args.port,
                proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
