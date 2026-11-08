# Architecture

## Existing system

The application is a single FastAPI service defined in [backend/app.py](backend/app.py). It serves [frontend/index.html](frontend/index.html) at `/`, mounts the frontend directory at `/static`, and provides JSON endpoints. The frontend contains inline CSS and JavaScript and sends requests to `location.origin`. There is no separate frontend service or build pipeline.

[backend/game.py](backend/game.py) loads mysteries, invokes optional AI moderation, and filters moderator output. Pydantic models validate API request/response shapes. See the [API inventory and run instructions](README.md).

## Request and state flow

1. Page initialization fetches `/api/mysteries`, selects the first entry, and creates a room. Start Game and Random Premise create new rooms and clear browser chat.
2. Creation reads the requested mystery JSON and allocates an eight-character UUID-derived ID and a four-letter code. Code generation checks the current code map for collisions, with up to 100 attempts. Room-ID collisions are not explicitly checked.
3. `ROOMS` maps IDs to mystery content, state, forbidden words, and room code. `CODE_MAP` maps codes to IDs. State includes question/hint counters, a solved flag, and sets of confirmed true/false fact indices.
4. Message, hint, and reveal routes resolve an ID first, then a normalized code if needed. The join endpoint exposes room metadata; no live room event stream or shared chat exists. The join UI is commented out.
5. Hints advance a room-local counter. Revealing returns the summary and sets `solved=true`. Further messages report game over. The frontend disables question controls after ending a game.

The browser keeps its room ID, transcript, title, and question count in JavaScript/DOM memory. Backend counters and frontend counters are separate; neither is a durable analytics system.

## Moderation and solving

Offline mode always returns an Unknown label with an offline nudge for ordinary input. Commands `/premise`, `/rules`, and `/help` are handled before moderation. The browser routes `/hint` to the hint endpoint; the message endpoint does not independently implement that command.

In AI mode, the OpenAI client sends the current input plus a system prompt containing the public premise, indexed private facts, acceptable solutions, and forbidden words. It does not send prior conversation messages. The hardcoded model is `gpt-4.1-mini`; the SDK uses Chat Completions with a `moderator_decide` function schema. No tool choice is forced. Missing tool calls fall back to Unknown.

The tool returns a label, optional nudge, and fact indices. Yes answers add indices to `confirmed_true`; No answers add to `confirmed_false`. All required facts confirmed true, or a Solved label, ends the game and returns the solution summary. The older string-similarity solution helper remains defined but its application call is commented out.

Output filtering replaces text containing a forbidden substring with Irrelevant. Hint and solution routes deliberately expose authored text without this filter. AskYesNo has an early response path outside the ordinary filtering path. Prompt instructions and substring filtering are imperfect spoiler controls; malformed tool JSON and upstream exceptions lack application-level recovery. Fact indices are filtered by integer type but not checked against mystery bounds.

## Mystery storage

[backend/mysteries](backend/mysteries) contains three JSON files. Fields include `mystery_id`, `title`, `premise_public`, `solution_summary`, `facts`, `forbidden_reveals`, `acceptable_solutions`, `hints`, and `metadata`. Facts have text and a required flag; helpers also accept legacy strings. Metadata includes difficulty and tags but is not returned by the listing endpoint.

Files are loaded directly without a formal schema validation layer. Mystery IDs are interpolated into paths without explicit validation; missing or malformed files are not translated into friendly API errors. Private facts remain on the backend except when supplied to OpenAI or intentionally revealed as hints/solutions.

## Deployment and persistence limits

Gameplay has no configured database, migration framework, task queue, or websocket layer. No container configuration or Render manifest is committed. The committed [Tests workflow](.github/workflows/tests.yml) runs offline pytest on Python 3.12 for pull requests targeting `main` and pushes to `main`; it has no deployment steps. External Render settings and live production behavior have not been inspected. Local startup is verified; no production deployment is implied. See the [deployment and release runbook](DEPLOYMENT.md) for manual verification, approval, staging, and rollback guidance; its Render settings are recommendations, not verified production configuration.

Optional [analytics instrumentation](ANALYTICS.md) now has backend hooks, typed event validation, and an explicitly supplied local SQLite adapter for isolated tests. Normal startup creates a disabled recorder with no database or environment activation; enabling production/staging collection is unsupported. Analytics metadata is separate from gameplay state, failures are contained without content logging, and no public analytics endpoint, background reconciliation, or production persistence is configured.

A separate [local analytics dashboard](README.md) now reads explicitly supplied local/test event files through a bounded read-only snapshot and returns aggregates. Its launcher binds only to loopback and is not imported by the gameplay app. Synthetic fixtures and data-quality warnings support development; no production/admin authentication, public analytics endpoint, or production collection is added.

Use one process/worker with the present design. State is lost on restarts and differs between workers/instances. Dictionaries have no expiry, persistence, explicit concurrency controls, or authentication boundary. AI requests run from synchronous route handlers; no application-level rate limit or cost guard exists.

## Proposed direction, not implemented

The agreed [roadmap](ROADMAP.md) starts with tests, CI, deployment safety, durable usage events, feedback, admin metrics, progressive hints, and reliability. Later phases add synchronized multiplayer, an AI generation pipeline with human review, and community authoring/engagement. These are future capabilities, not features in the current source.

Durable analytics storage, shared multiplayer state, identity/admin access, generation orchestration, and publication controls need separate technical designs. No storage engine, transport, hosting topology, or new framework has been selected here. Preserve the single-service architecture until concrete requirements justify a change; none is introduced by these documents.
