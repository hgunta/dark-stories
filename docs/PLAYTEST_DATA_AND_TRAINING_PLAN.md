# Dark Stories: Privacy-first playtest data collection and moderator training plan

**Status: architecture proposal only — NOT activated, NO transcript collection change.**
**Purpose:** Turn real-game moderator mistakes into trusted evaluation examples
without silently collecting conversations. November 2026.

## Current implementation and data loss warning

- `backend/app.py` initializes `FeedbackStore()`, a **process-local bounded**
  dictionary containing only `(mystery_id, rating, issue)` keyed by internal
  room ID. It is lost on process restart/deploy. The feedback endpoint is
  accessible only after a finished game.
- `ROOMS`, including chat/question events, are process-local and expire
  after inactivity; no database persists chat. Private guesses aren't written
  into shared room events.
- `AnalyticsRecorder()` is disabled by default and its existing SQLite
  adapter explicitly rejects production activation. It stores category
  metadata, not raw user text. A separate SQLiteFeedbackStore exists for
  explicit local use, not Render production.
- **Existing play sessions cannot be recovered as transcripts from the
  app** after restart/expiration. Screenshots or voluntarily exported data
  can become labeled tests only after permission.

## Two separate opt-ins / data classes

### 1. Anonymous, structured game metrics (default only after disclosure)

Data: randomized non-account session key; case ID / version; model and
moderator prompt revision; timestamps rounded to useful granularity; number
of questions, hints, reveals and correct solves; answer category counts;
post-reveal satisfaction rating, issue type, optional "want another case".
No prompt text, raw chat, invite code, emails, names, IP addresses or
device fingerprinting. If a genuinely nonessential metric is not disclosed,
do not collect it.

Goal: determine whether cases are fun and where moderator behavior fails.
Suggested retention: 90 days of session-granular events, then
aggregate-only reports. Explicitly implement deletion/retention jobs.

### 2. Player-authorized transcript contribution (unchecked, per session)

Offer a clearly visible, **unchecked** choice:
"Share this play session's questions and moderator responses to improve Dark
Stories. Your messages may be read by reviewers and used in evaluation or
training. You can play without sharing."

- Consent before storing any message text. For multiplayer, collect **no
  combined transcript unless all participants consent**; simpler first
  implementation: offer only single-player transcript sharing.
- Keep the choice separate from rating submission. Refusal cannot affect
  gameplay, answers, scores or access.
- Store only text needed for debugging moderator quality: user question,
  label returned, whether game was solved, and later human correction.
  Avoid raw model system prompts, API keys, room join codes, or user IDs.
- Restrict input size (e.g. <=1000 characters per message), per-session
  question count and storage quotas. Detect obvious PII or secrets, remove
  before review, provide reporting/deletion controls, and warn users not
  to enter sensitive personal information.
- Encrypt in transit and at rest. Restrict read/export permissions to
  authorized project reviewers. Do not publish transcript data in
  GitHub issues, Actions logs, PRs or the open web.
- Suggested retention: raw opt-in transcripts <=30 days; reviewed,
  redacted, consent-authorized labeled examples <=180 days, then delete
  unless separately agreed. Retention is an actual scheduled deletion job,
  not a vague policy statement.
- Provide a generated deletion receipt token stored only client-side,
  hashed server-side, to let a person withdraw/deletion-request without
  needing an account. Revocation should remove eligible raw and training
  records plus indexes/backups per the documented deletion schedule.

**No collection at all should be activated without explicit owner sign-off
on notice, consent wording, data host, retention and deletion policy.**

## Durable implementation: Render Postgres, not the ephemeral app container

Use a separate small Render Postgres database or other managed encrypted
service. Current Render preview runs on a single web service, whose local
filesystem is not a durability guarantee. Backups and retention must be
configured appropriately; use minimal permission accounts.

Proposed tables:

```sql
CREATE TABLE game_sessions (
    session_id uuid PRIMARY KEY,
    case_id text NOT NULL,
    case_revision text NOT NULL,
    moderator_model text NOT NULL,
    prompt_revision text NOT NULL,
    started_at timestamptz NOT NULL,
    solved_at timestamptz,
    solved_by text,
    question_count integer NOT NULL DEFAULT 0,
    hints_used integer NOT NULL DEFAULT 0,
    feedback_rating smallint,
    issue_code text,
    expires_at timestamptz NOT NULL
);

CREATE TABLE transcript_consents (
    session_id uuid PRIMARY KEY REFERENCES game_sessions(session_id) ON DELETE CASCADE,
    consented_at timestamptz NOT NULL,
    revoked_at timestamptz,
    deletion_token_digest text UNIQUE NOT NULL
);

CREATE TABLE transcript_events (
    session_id uuid NOT NULL REFERENCES transcript_consents(session_id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    asked_at timestamptz NOT NULL,
    player_text_redacted text NOT NULL,
    moderator_label text NOT NULL,
    reviewer_correct_label text,
    reviewer_notes_redacted text,
    PRIMARY KEY (session_id, ordinal)
);
```

**This is illustrative schema, not a ready-to-run migration.** In production
enforce consistent consent state transactionally and reject/reconcile events
from revoked sessions. Keep IDs random and unlinked to real identities.
Use separate credentials for ingestion, review and cleanup. Avoid
secret-containing query logs. If a user opts out, only `game_sessions`
should remain, without transcript rows.

## Example from the Fifth Name failure

**Player's theory**: “The same person was listed twice, so the firefighters
thought five residents were accounted for, but only four were actually safe,
and they went back to find the fifth person.”

Observed moderator: `AlmostSolved`, followed by an inappropriate repeated
“explain how the pieces fit together” prompt.

**Correct human label**: `Solved` (full causal explanation). No requirement
to infer “former and current surnames”; those are incidental story dressing.

**Training/evaluation record:**

```json
{
  "case_id": "ex-001",
  "task": "solve_judgment",
  "input": "The same person was listed twice, so only four unique people were safe, and the fifth was missing.",
  "model_output": "AlmostSolved",
  "human_gold_label": "Solved",
  "reason_code": "correct_causal_explanation_wrongly_downgraded",
  "case_revision": "reviewed_v1"
}
```

This example is derived from owner-provided text, not a claim that existing
private chat logs were retrieved.

## High-value labels for future evaluation

- `Yes` / `No` / `Irrelevant` / `Unknown` / `AlmostSolved` /
  `Solved`, plus the **corrected** label.
- Distinguish `true_partial_denied`, `complete_solution_denied`,
  `incorrect_win`, `premature_spoiler`, `case_underdetermined`,
  and `bad_prompt_hint`.
- Attach the particular *case revision* and the reviewed minimum sufficient
  solution, so annotations still make sense after story rewrites.
- Human reviewer must confirm correctness against the canonical solution
  and plausible alternative explanations; bad AI outputs should NEVER
  become training targets without correction.
- Maintain a frozen regression set of real mistakes before model training.
  Compare prompt/model changes on that set and on a held-out sample
  separated by play session, ideally case, to avoid leakage.

## Fine-tuning caveat (November 2026)

OpenAI's current public API pricing documentation says its fine-tuning
platform is **being wound down and is unavailable to new users**.
Do not plan a product roadmap that assumes fine-tuning Luna is available.
First leverage **prompt revision, case-specific minimum sufficient solutions,
separate semantic adjudication and a versioned regression set**.
After enough consented, high-quality correction examples, confirm available
provider-specific training/fine-tuning options and their data policies.
Model evaluation should come before any training purchase.

Public status source: https://platform.openai.com/pricing/

## Suggested phases

1. **Now:** Fix recognition bug and retain regression tests from screenshots.
   Continue structured feedback only, with explicit notice that it is currently
   not durable.
2. **Next approved build:** Add Postgres-backed ratings and case-version
   aggregate counters (no chat text), consent UI and data handling policy.
3. **Later approval:** Opt-in transcript collection with deletion receipt,
   restricted review console, vetted gold-label exports and periodic purge.
4. **Only after evidence:** Evaluate alternate moderator models/prompts on
   frozen failures, then consider training *if a supported platform exists*.
