# Neon-backed full conversation histories — preview rollout

**Status as of November 12, 2026:** Implemented and tested against real disposable PostgreSQL; **Neon project connection not yet verified**. No raw chat collection is enabled without a configured database AND affirmative per-session consent.

## Scope and exact stored content

- Only experimental preview cases (`ex-001`, `ex-002`).
- **Without transcript opt-in:** anonymous session UUID, case ID and revision, questions asked (count), hints (count), outcome, optional feedback rating and issue code. Absolutely no player text or moderator message text in the playtest database.
- **After explicit opt-in:** each subsequent completed interaction in time order: ordinal, UTC timestamp, event type, redacted player message (when applicable), model's moderation label and **the exact displayed moderator reply**, as well as hint text and the final reveal when requested. Consent is not retrospective.
- No account identifiers, IP addresses, four-letter room codes, eight-character room IDs, chat join codes or raw consent credentials in the data tables.
- Consent can only be enabled by the original single-player creator using a separate high-entropy key. Joining a shared room disables transcript collection and deletes previously contributed text.
- Opt-in issues a copyable deletion receipt. A valid receipt deletes the consent row and cascades to **all transcript rows**, while preserving only the anonymous structured metrics. Backend rejects subsequent text writes even if the application server is stale.
- Input and output both have bounded length and mask common email addresses, phone numbers and URLs. **This is not perfect de-identification**; reviewers must re-screen records. No public transcript retrieval API.
- Human-review JSONL exports include input, output, model label and blank human correction fields; exports are not automatically approved for training.

## Provider compatibility

The backend uses **standard psycopg PostgreSQL**, not a Render-specific SDK. It can use Neon PostgreSQL unchanged once connected. The schema migration adds `moderator_text` to existing consented-transcript rows while preserving old fields.

Neon is not a drop-in way to provide *active multiplayer room continuity*. Those rooms still use process memory. This rollout only handles playtest feedback and explicitly consented histories.

### How to activate Neon securely

1. In the Neon console (or via connected Neon management when available), create an ordinary PostgreSQL project in a US region near Render's Oregon preview deployment. Choose the **free tier** and avoid paid add-ons.
2. From Neon's **Connect** dialog, copy the application's **PostgreSQL connection string** with TLS/SSL required (typically `sslmode=require`). Keep the username, password and hostname private.
3. In [Render preview → Environment](https://dashboard.render.com/web/srv-dbpo3tajnfac73bskjj0), set:
   - `DARK_STORIES_PLAYTEST_DB_URL`: the complete Neon connection string
   - `DARK_STORIES_PLAYTEST_ENABLED`: `true`
4. Save and redeploy **preview only**. Do not paste the DSN into ChatGPT, GitHub source, Issues, logs or screenshots.
5. Inspect `https://dark-stories-preview.onrender.com/api/playtest/status`: `{"enabled":true}` should appear **only once the DB connection and schema initialization succeed**. When it is false, consent and experimental rating controls are hidden.
6. Open an experimental case, choose to share, ask a question, request a hint and reveal/solve, then save the deletion receipt. Test deletion via the experimental-case list before recruiting others.

**No real Neon project credentials were supplied in this turn.** A successful disposable PostgreSQL test does not prove a Neon project has been provisioned, connected or live-verified.

### Test coverage

- `tests/test_playtest_collection.py`: complete ordered input/reply pairs; hint/reveal; no text without opt-in; no retroactive recording; creator-only permission; transcript revocation and multiplayer purging; backward-compatible gameplay.
- `tools/verify_playtest_postgres.py`: integration test with a real disposable PostgreSQL server; verifies stored output, order, redaction, ratings, deletion and no post-revocation write.
- `tools/export_playtest_review.py`: privileged local review export; no automatic fine-tuning.

### Retention and backups

The existing application enforces **lazy** deletion of transcript rows older than 30 days and anonymous session data older than 90 days on new experimental game starts. This is *not* a wall-clock guarantee. Before inviting general users, add an independently scheduled daily purge or a provider-supported database retention job with audit checks, and configure a reviewed backup policy. Avoid storing sensitive data you cannot adequately secure or erase.

If Neon is on a free tier, check the account's current compute/storage/restore allowance. The old **Render free database**, created earlier, expires December 12, 2026 and is **not used** in the Neon deployment. No paid Render database was created.

### Why human review matters

Moderator outputs may be wrong. The exporter sets `human_gold_label=null` and `approved_for_training=false` for every row. Human reviewers should label false negatives (like a complete answer mistakenly graded AlmostSolved) and false positives before producing training or held-out evaluation sets. Raw conversation dumps are **not** a reliable fine-tuning dataset.
