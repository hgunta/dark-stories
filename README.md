# Dark Stories

Dark Stories is a lateral-thinking mystery game: read a puzzling premise, ask yes/no questions, request hints, and propose an explanation. An optional AI moderator knows the private solution. The current browser experience is single-player.

## Stack

- Python with FastAPI and Pydantic models; Uvicorn serves the application.
- One vanilla JavaScript, HTML, and CSS page; no frontend build or Node dependencies.
- JSON mystery files and process-local room dictionaries; no database.
- `python-dotenv` for environment loading and the OpenAI Python SDK for optional moderation.

See [architecture](ARCHITECTURE.md), [product direction](PRODUCT.md), [roadmap](ROADMAP.md), [agent instructions](AGENTS.md), the [deployment and release runbook](DEPLOYMENT.md), and the [usage analytics design](ANALYTICS.md).

## Local setup

From an existing checkout's root, use Python 3.12 (verified during documentation validation). The source requires Python 3.10+ syntax, but other versions have not been validated here. No Python version or dependency versions are pinned.

```bash
python3 -m venv /tmp/dark-stories-docs-venv
/tmp/dark-stories-docs-venv/bin/python -m pip install --no-cache-dir -r backend/requirements.txt
/tmp/dark-stories-docs-venv/bin/python -m pip check
cd backend
USE_API=false PYTHONDONTWRITEBYTECODE=1 /tmp/dark-stories-docs-venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

The virtual environment is outside the checkout to avoid adding local artifacts; `/tmp` is temporary, so recreate it when removed. These are POSIX shell instructions. Visit `http://127.0.0.1:8000` locally. Stop with Ctrl+C. Optional `--reload` enables development reloads but clears active rooms when the server restarts. Use one worker.

The backend requirements include `uvicorn[standard]`; the root requirements list plain `uvicorn`. Both include FastAPI, python-dotenv, and openai. Use the backend file for this workflow.

## Offline and AI modes

Offline is the default (`USE_API=false`). It needs no API key. Ordinary questions return `Unknown. (offline mode)`; room creation, hints, reveals, and restarting remain available. It is a development stub, not a reasoning engine, and cannot solve questions automatically.

For AI moderation, securely supply `OPENAI_API_KEY` in the process environment or a local ignored `.env`, then start the same server with `USE_API=true`. Never commit or paste credentials into documentation. `load_dotenv()` uses its normal discovery behavior; the application does not explicitly select a dotenv path. Both `.env` and `backend/.env` are ignored.

The SDK calls OpenAI Chat Completions using the hardcoded `gpt-4.1-mini` model, temperature 0.2, a 30-second request timeout, and the `moderator_decide` function tool. API access and quota are required. Missing a key in AI mode prevents startup. Live AI access and output quality were not validated for this documentation.

## Existing HTTP interface

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/` | Serve the frontend HTML |
| GET | `/static/index.html` | Frontend file through the static mount |
| GET | `/api/mysteries` | List mystery IDs and titles |
| POST | `/api/create_room` | Create a room; JSON `{"mystery_id":"ms-001"}` (field defaults to `ms-001`) |
| GET | `/api/join/{room_code}` | Look up a room using a case-insensitive code |
| POST | `/api/message` | Ask a question, propose an explanation, or send `/premise`, `/rules`, `/help` |
| POST | `/api/hint` | Return the next hint, then `No more hints.` |
| POST | `/api/reveal` | Return the solution and mark the game ended |
| GET | `/docs`, `/redoc`, `/openapi.json` | FastAPI's generated API documentation/schema |

Message, hint, and reveal bodies share the schema `{"room_id":"<returned room_id>","text":"Was it an accident?"}`. `text` is required even for hint/reveal, where its contents are ignored. `room_code` can replace `room_id`; a valid ID takes precedence when both resolve. Responses contain `reply` and `solved`. Unknown rooms return 404. Invalid mystery IDs are not handled as a friendly client error.

To inspect the running service:

```bash
curl -fsS http://127.0.0.1:8000/api/mysteries
curl -fsS http://127.0.0.1:8000/openapi.json
```

## Automated tests

From the repository root, create a clean test environment and run:

```bash
python3 -m venv /tmp/dark-stories-test-venv
/tmp/dark-stories-test-venv/bin/python -m pip install --no-cache-dir -r requirements-test.txt
/tmp/dark-stories-test-venv/bin/python -m pip check
env -u OPENAI_API_KEY USE_API=false PYTHONDONTWRITEBYTECODE=1 /tmp/dark-stories-test-venv/bin/python -m pytest -q -p no:cacheprovider
```

`requirements-test.txt` includes the existing backend requirements plus pytest and HTTPX (required by FastAPI's TestClient). No running server is needed. The suite uses in-process requests, resets room dictionaries and environment per case, disables dotenv loading, blocks real OpenAI client construction and socket connections, and uses deterministic room identifiers. AI cases enable the classifier only with a fake completion client; no credentials or paid calls are required. Local dotenv credentials are never loaded.

Tests cover the three mystery listings/creation, joins and unknown rooms, offline questions, ordered hints/exhaustion, reveal/game-over, mocked moderation, confirmed facts and solve detection, and independent rooms. Known limitations are characterized explicitly: invalid mystery IDs raise file errors, malformed AI JSON/upstream errors propagate, and integer fact indices are not bounds-checked. These passing characterization tests describe current behavior rather than endorsing it. Browser rendering, live AI quality, concurrency, persistence, and production are outside this suite. The GitHub Actions workflow described below runs this suite.

## Continuous integration

[Tests](.github/workflows/tests.yml) runs on pull requests targeting `main` and pushes to `main`. The `pytest (Python 3.12)` job uses a GitHub-hosted Ubuntu runner, sets up Python 3.12, installs `requirements-test.txt`, runs `python -m pip check`, and executes the complete existing pytest suite from the repository root:

```bash
env -u OPENAI_API_KEY python -m pytest -q -p no:cacheprovider
```

The job sets `USE_API=false` and `PYTHONDONTWRITEBYTECODE=1`; it unsets `OPENAI_API_KEY` for the test command. AI calls remain mocked by the test fixtures. No OpenAI, GitHub, or Render secrets need to be configured. The workflow uses only `contents: read` for the automatic GitHub token, does not persist checkout credentials, and adds no caches or deployment steps. It does not merge PRs or change repository settings.

To view results, open a pull request's **Checks** tab, select **Tests**, then open the **pytest (Python 3.12)** job and its install, dependency-check, and test logs. Repository-wide history is under **Actions → Tests**. A failed command fails the job. Branch protection is not configured by this workflow, so it does not itself require checks before merging.

A branch push alone does not trigger this workflow unless the branch is `main`; open a PR targeting `main` to validate a feature branch. If Actions is disabled or GitHub requires approval for a fork contribution, a repository maintainer must enable/approve execution through GitHub. No production configuration changes are needed. Local test success does not establish that a hosted Actions run passed.

## Local analytics dashboard (development only)

The dashboard is a **separate loopback-only server**; normal `app:app` startup remains unchanged, analytics stays disabled, and no dashboard/report routes are added to the game. Use an existing environment installed from `requirements-test.txt` as above. From the repository root in a POSIX shell:

```bash
sample_dir=$(mktemp -d)
PYTHONDONTWRITEBYTECODE=1 /tmp/dark-stories-test-venv/bin/python -m backend.analytics_sample --database "$sample_dir/events.sqlite3"
PYTHONDONTWRITEBYTECODE=1 /tmp/dark-stories-test-venv/bin/python -m backend.analytics_dashboard --database "$sample_dir/events.sqlite3" --environment test --mode ai
```

Open `http://127.0.0.1:8765` in your **local** browser. Stop with Ctrl+C. The generator prints **SYNTHETIC SAMPLE ONLY**, marks every event, refuses existing filenames, and never reads player data or calls OpenAI. It creates six synthetic games with solved, revealed, recent, zero-question, offline, and incomplete-response cases. The dashboard labels this dataset explicitly. Keep the temporary database only as long as needed; it is not provisioned storage or evidence of Render durability.

The launcher is fixed to `127.0.0.1`, with forwarded-header trust disabled. Host, peer-address, and browser-origin checks reject remote/cross-origin access. Do not proxy, tunnel, port-forward, publicly bind via another server, or deploy this development tool; it has **no admin authentication** and trusts local machine access. No Render/GitHub setting or production database is configured. A shared/multi-user or remotely accessible dashboard requires a separate authenticated design.

The page shows starts, question attempts/responses and averages, solve/reveal rates, hints, mystery samples, and incomplete-event counters. Rates use starts at least 30 minutes old; averages include zero-question starts. Empty denominators show N/A. `--mode offline` views the offline cohort separately; `--environment local` selects explicitly captured local events from an existing database. Production/staging environments are rejected. `--port` can select another local port (default 8765); no `--host` option exists.

Reads use a read-only consistent SQLite statement snapshot, capped at 10,000 events per environment. Over-limit, malformed, or unavailable databases return an error instead of partial metrics. The UI exposes aggregate counts only, not raw events/IDs. Abandonment and replay are unavailable. Low mystery sample sizes are not difficulty rankings, and incomplete/mixed-mode games must not be interpreted as reliable outcomes. See [analytics reporting semantics and limitations](ANALYTICS.md).

## Validation and known limitations

For browser changes, also manually verify page load, a question, hint exhaustion, reveal, and Start Game; offline questions should return the stub response. DS-001 validation exercised every existing mystery through create/join/message/hint/reveal/game-over requests.

Rooms, codes, counters, and confirmed facts are held only in memory. Restarts lose them; multiple workers/instances do not share state. Rooms have no expiry. Browser chat is not persisted or synchronized. Joining exists in the API, but its UI is commented out. Sharing is available after either solving or revealing and currently uses “I solved” wording for both. Some end-game instructions refer to a missing “New Room” button; use Start Game.

There is no authentication, rate limiting, database, or robust recovery for AI/network failures. Spoiler filtering uses substring checks and is not a guarantee. Dependencies are unpinned, and Python bytecode is tracked in the existing repository. No Render manifest, Dockerfile, or production start configuration is committed; external deployment settings are unverified. This project documentation does not authorize production changes or deployment.
