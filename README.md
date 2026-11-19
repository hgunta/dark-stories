# Dark Stories

Dark Stories is a lateral-thinking mystery game: read a puzzling premise, ask yes/no questions, request hints, and propose an explanation. An optional AI moderator knows the private solution. The current browser experience is single-player.

## Stack

- Python with FastAPI and Pydantic models; Uvicorn serves the application.
- One vanilla JavaScript, HTML, and CSS page; no frontend build or Node dependencies.
- JSON mystery files and process-local room dictionaries; no database.
- `python-dotenv` for environment loading and the OpenAI Python SDK for optional moderation.

See [architecture](ARCHITECTURE.md), [product direction](PRODUCT.md), [roadmap](ROADMAP.md), [agent instructions](AGENTS.md), the [deployment and release runbook](DEPLOYMENT.md), the [usage analytics design](ANALYTICS.md), and the [production analytics readiness plan](PRODUCTION_ANALYTICS_PLAN.md).

## Mystery library and owner review

Dark Stories is prioritizing a **browsable, shareable mystery library**, rather
than a scheduled daily mystery. The first editorial batch adds nine original
draft cases (ms-004–ms-012), bringing the repository's catalog to **12**.
The normal homepage lists case titles with difficulty, includes Random Premise,
and has **Share This Mystery**, which generates a spoiler-free `?case=ms-xxx`
link that starts the same puzzle in a fresh, independent game for a friend.
No account or daily return is needed. This is separate from the existing
room invite link for synchronized players.

**Review new puzzles with a single action, every time you add one:**

1. Add `backend/mysteries/ms-013.json` (or the next unique numbered
   ID), using an existing case as a starting template. Include the full
   solution, required facts, allowed answers, spoiler terms, hints and metadata.
2. In your local repository folder, **double-click
   `review-mysteries.command` on macOS** or **`review-mysteries.bat`
   on Windows**. Alternatively run `python tools/review_mysteries.py`
   on any system. The launcher automatically rebuilds and opens the private
   Review Desk with **every current mystery file**; no separate generation step.
3. The reviewer opens at the first **new or changed** puzzle. Inspect its
   premise and hidden solution/facts, hints, accepted answers and spoiler
   terms. Use its local-game link to play that particular case on a locally
   running server when you want to test AI behavior.
4. Mark **Needs revision** or **Approved for playtesting**, complete the
   checklist, and save notes. A puzzle edited after approval will be flagged
   for fresh review (based on a content fingerprint). Prior notes remain
   available, but the approval is no longer treated as current.
5. Click **Export my reviews (JSON)** regularly as a backup. You can restore
   those notes later with **Import previous reviews**. Reviews are kept
   browser-locally between rebuilds; importing is useful when browsers or
   devices change.

The launcher uses Python's standard library and does not require an
OpenAI key or internet connection. On macOS, you may need to grant the
downloaded shell launcher permission to execute; the Python command works
as a fallback. If you don't have a local checkout, download the repo,
extract it, and run the launcher there. **This is a local reviewer, not a
public admin page.**

The generated HTML includes **private solutions**: never publish it to the
web, put it in public GitHub pages, or link it in the deployed app. Reviews
are a local editorial aid, not a publishing flag or live AI test. Real AI
moderation and solve fairness still require human test sessions with
`USE_API=true` and a separately approved API budget. See
[MYSTERY_EDITORIAL_REVIEW.md](MYSTERY_EDITORIAL_REVIEW.md) for case-by-case
risks, and [EARLY_STAGE_STRATEGY.md](EARLY_STAGE_STRATEGY.md) for the
traffic-appropriate launch experiment. The draft cases should not be
considered quality-approved or production-tested until that review finishes.

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

## Player feedback MVP (preview, non-durable)

After a player solves or reveals a mystery, an optional rating (1–5) and a fixed
issue-category selector appear. Sending feedback does not affect gameplay.
The `POST /api/feedback` endpoint accepts only the current room ID, a strict
integer rating and one of `none`, `confusing_clues`, `incorrect_answer`,
`spoiler` or `other`. Raw comments, private story text and player identity
are not accepted. One submission per completed room; no public listing API.

**Important: this first increment is not durable.** Feedback is held in a
bounded process-local dictionary and disappears after restart/redeploy.
The current Render service has no verified persistent filesystem; no production
feedback metrics, backup/recovery, or owner dashboard is claimed. Treat any
feedback as a temporary preview, not a reliable reporting or issue-tracking
system. Production persistence, retention/deletion policy, abuse prevention and
private reporting require a separately reviewed increment before depending on
this feature as a source of player insights.

## DS-007B — Explicit local SQLite feedback and private aggregate export

The `backend.feedback_storage.SQLiteFeedbackStore` adapter now supports an
**explicitly selected local SQLite file**. It can preserve structured ratings
and issue categories across restarts of a **local** server. The default
`uvicorn app:app` startup is unchanged and continues to use the existing
non-durable in-memory feedback store. No Render storage or new paid service
has been provisioned or activated.

To run a **local-only** feedback-backed game, install the documented test
environment, then from the checkout root use:

```bash
feedback_dir=$(mktemp -d)
USE_API=false /tmp/dark-stories-test-venv/bin/python -m backend.feedback_local --database "$feedback_dir/feedback.sqlite3"
```

Open `http://127.0.0.1:8000` on the same computer. After completing a
mystery, submit a 1–5 rating and optional issue category. Stop the server
with Ctrl+C. Restart with the **same** database path to retain previous
feedback. Choose a path in a private folder; keep this SQLite file and
backups out of Git. Do not bind, reverse proxy, forward, or expose this
development launcher to remote users.

For an **owner-only, local aggregate report**, run:

```bash
/tmp/dark-stories-test-venv/bin/python -m backend.feedback_report --database "$feedback_dir/feedback.sqlite3"
```

The JSON report shows counts, average rating, rating distribution, issue
categories and mystery-level averages. It never outputs individual room
IDs or stored digests, and no public reporting endpoint is added. The
store uses an internal per-file random HMAC salt to avoid keeping raw room
identifiers. It rejects duplicate submissions for the same room even if
the SQLite store is reopened. This does not provide durable gameplay
rooms; those remain in-memory and disappear on restart.

An optional owner-invoked 30-day expiry command is available:

```bash
/tmp/dark-stories-test-venv/bin/python -m backend.feedback_report --database "$feedback_dir/feedback.sqlite3" --prune-expired
```

**Not a production launch.** Expiry is not scheduled and neither a disk
nor a local SQLite file is a backup. We have not verified durable Render
volume access, real production retention/deletion, recovery, rate limiting
or administrative access. The local exporter has no authentication and
must remain on an owner-controlled machine. Before real durable player
feedback can be collected in production, select and verify a persistent
provider/storage path, approved retention/backup controls and a secure
owner export workflow; treat the default in-memory experience as a
non-durable preview until then.

## DS-010A — Recoverable game errors

Invalid mystery IDs now return a plain HTTP 404 instead of an unhandled file
error. When the AI moderator times out, returns malformed output, or fails,
the game returns a sanitized HTTP 503 with a request-to-retry message. Error
responses never include upstream exception prose, private player questions,
or mystery facts. The existing analytics error code still records the failure
when the opt-in test recorder is enabled. A failed moderator call does not
mark the room solved or consume a successful question response.

The browser displays a friendly retry message after failed room creation,
questions, hints, and reveals. It retains the previous game if starting a
new room fails, preserves an unsent question for retry, and ignores responses
from an earlier room if the player has started a different mystery.

This is an incremental reliability fix, not the full DS-010 scope. Rate
limiting, room expiry/cleanup, concurrent gameplay safeguards, upstream
retry/backoff policy, and a tested production deployment remain outstanding.
No new dependencies, infrastructure, database or analytics activation are
introduced.

## DS-010B — Idle room expiry

Game rooms now expire after **two hours without successful room access**.
Creating a game, joining, asking a question, requesting a hint, revealing a
solution, or submitting feedback cleans up stale rooms first. Access to a
live room renews its idle deadline. Expiry removes the in-memory room state
and its four-letter join-code mapping together; old rooms cannot be resumed.
Missing and expired rooms both return the existing generic HTTP 404
(`Room not found`) without disclosing whether a code was previously valid.
The browser explains that the game is no longer available and offers the
existing Start Game action.

Cleanup is **lazy**, performed when a room-related request arrives. This
is not a background scheduler: if there are no incoming room requests,
expired objects remain in this process until the next one. A monotonic
clock measures inactivity, with fake-clock tests; restarts still clear
all rooms. Room/gameplay state remains process-local and is not shared
across workers. This increment does not add automatic abandonment
tracking, retention for feedback records, API rate limiting, durable
rooms, or concurrency guarantees for simultaneous game actions.

## DS-010C — Process-local gameplay rate limits

The backend now applies sliding-window request limits **before** expensive
moderator classification or room creation:

- **30 new rooms per 60 seconds** across the running server process.
- **15 moderator questions per room per 60 seconds**.
- **120 moderator questions per 60 seconds** across the process, regardless
  of which room issued them.

Excess requests return HTTP **429** with a generic retry message and
`Retry-After` (whole seconds). Rejected requests do not call the paid AI
moderator, consume hints, advance solve state, or use another quota slot.
Browser users see a polite wait-and-retry message, and their question input
is retained for retry. Local `/help` and `/premise` responses, hint/reveal
requests, and completed-room responses remain available when the question
quota is exhausted.

Rate-limit state contains only ephemeral room identifiers and timestamps.
It does **not** inspect or store IP addresses, browser fingerprints, question
text, or user identities. Idle limiter entries are pruned lazily as requests
arrive. No new dependencies, storage service, or metrics activation.

**Important:** This is a first-layer safeguard, not a guaranteed cloud-wide
AI budget. Limits are shared by legitimate players behind one application
process, so bursts across users can produce temporary 429s. Restarting the
process resets limits, and multiple Render workers/instances each maintain
independent counters; this does not ensure a global cap across replicas.
There is no simultaneous in-flight request cap, per-account enforcement,
upstream cost quota, or protection at a reverse proxy/CDN. Confirm actual
Render worker configuration and OpenAI billing limits before depending on
this for monetary protection. Thresholds should be tuned against real
traffic only after privacy-approved usage data is available.

## Phase 2A — Shared room invites and public activity (single-process preview)

Create or start a mystery and use **Copy Invite Link** to share a URL like
`/?room=ABCD`. A second browser opening that URL joins the same in-memory
room; alternatively enter the four-letter code in **Join a room**. Both
browsers see the same public premise and shared activity, refreshed every
three seconds. Public yes/no questions and brief moderator labels are
recorded in order; hints and the public fact that a room was solved/revealed
are also shared. The log holds at most 100 entries per room, with up to
400 characters per question. The existing game-state counters and solve
status are shared by both browsers while they reach the **same server
process**.

**Public/private boundary:** The shared timeline never includes private
mystery facts, acceptable solutions, the solution summary, or the text of
a recognized successful solution guess. The submitting browser may
receive a solution response, but the feed broadcasts only the ended
state. However, **regular questions ARE public to other participants**,
including unsuccessful hypotheses typed into the regular question field.
Do not treat the existing question field as a confidential solution
submission channel. A separately designed and tested private-guess API,
participant authentication/identity and visibility policy are needed
before declaring the full Phase 2 privacy acceptance criteria complete.

**Prototype limits:** This is not robust production multiplayer. Four-letter
codes are weak invite secrets; existing code-based joining does not prove
an invitation or authenticate participants. There is no separate
authorization layer for reading shared events or revealing a room.
Multiple server processes/Render instances do not share rooms or logs.
Events are not durable across restarts, simultaneous AI calls may finish
out of order, and polling is not WebSocket push. The read-only polling
endpoint does not renew the two-hour inactivity timer. No infrastructure,
deployment, server setting or live analytics collection was changed by
this PR. A production rollout needs stronger invite tokens, a private
submission contract, concurrency controls, shared state and session
recovery.

## Phase 2B — Private solution submissions (preview)

A separate **Submit a private solution** form sends a guess to
`POST /api/private_guess` with `room_id` and `guess`. The guess is checked
without publishing its text or a moderator explanation in the shared feed.
The response is returned **only to the submitting HTTP request**:
incorrect guesses say to keep investigating, and successful guesses end the
room, with a public `solved` event that contains neither the guess nor the
solution. Private submissions do not record confirmed facts or mutate the
public question timeline. Validation rejects empty/oversized guesses and
additional fields; existing per-room and global AI-question quotas also
protect the private endpoint.

**Privacy scope and limitations:** Normal chat questions in
`POST /api/message` are **still public**, including unsuccessful hypotheses
submitted there. A player who wants privacy must use the separate private
solution form. A correct private guess changes the shared solved status for
everyone and disables further play; the fact that a solve occurred is public.
The API does not store private guess text as room history or in analytics
events. Requests do pass through the server and (in AI mode) to the OpenAI
moderator, so this is not end-to-end encryption or a promise that no external
service processes the guess. In offline mode, a conservative text-similarity
fallback is used for local testing; it is not a replacement for semantic
solution validation.

There are no player accounts or identity-bound access controls: anyone
holding a room identifier can submit a guess and can use the existing
public endpoints. The four-letter invite code is not authenticated or a
robust secret. A private-guess response is not readable through the
public room feed, but the submitting browser is responsible for its own
local display. Concurrency handling is limited to a final atomic
solved-state check; full multi-process synchronization and reliable
reconnection remain future Phase 2 work. This PR does not deploy or
provision infrastructure or enable production analytics.

## Validation and known limitations

For browser changes, also manually verify page load, a question, hint exhaustion, reveal, and Start Game; offline questions should return the stub response. DS-001 validation exercised every existing mystery through create/join/message/hint/reveal/game-over requests.

Rooms, codes, counters, and confirmed facts are held only in memory. Restarts lose them; multiple workers/instances do not share state. Inactive rooms expire after two hours, with lazy cleanup on room-related requests. Browser chat is not persisted or synchronized. Joining exists in the API, but its UI is commented out. Sharing is available after either solving or revealing and currently uses “I solved” wording for both. Some end-game instructions refer to a missing “New Room” button; use Start Game.

There is no authentication, shared cross-instance rate limiting, default durable gameplay database, or complete AI/network recovery strategy. Spoiler filtering uses substring checks and is not a guarantee. Dependencies are unpinned, and Python bytecode is tracked in the existing repository. No Render manifest, Dockerfile, or production start configuration is committed; external deployment settings are unverified. This project documentation does not authorize production changes or deployment.
