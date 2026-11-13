# Preview Playtest Collection — implementation and safe activation

**Status:** Staging-validated; activation requires a database connection **secret set only in Render**. Never add credentials to GitHub or ChatGPT messages. Main production remains untouched.

## Preview pilot resources

- Render preview app: [dark-stories-preview](https://dashboard.render.com/web/srv-dbpo3tajnfac73bskjj0)
- Free temporary Postgres: [dark-stories-preview-playtest-pilot](https://dashboard.render.com/d/dpg-dbr0kkmtlv9c73dc2vc0-a) (ID `dpg-dbr0kkmtlv9c73dc2vc0-a`, Oregon)
- **Expires December 12, 2026.** Render's free databases expire after 30 days, do not have backups, and should not be trusted for production or long-lived data.
- **Cost:** free plan $0/month; if later approved, the smallest paid Postgres offering is approximately $6/month, subject to Render billing/pricing at the time of upgrade.

Source: https://render.com/docs/free and https://render.com/pricing/

## Privacy behavior by default

- Only **experimental** cases (`ex-001` and `ex-002`) have durable data collection. Existing live/main cases keep their previous process-local anonymous ratings.
- When the database is configured, experimental rooms record a random UUID, case ID/revision, number of moderator interactions/hints, solve or reveal outcome, optional rating (1–5) and issue type. **No message text, IP, email, room ID, room code or device fingerprint is put in the playtest database by default.**
- The interface presents a separate, **unchecked** opt-in box. Only future questions/private theories and moderator labels are eligible; it never retroactively copies prior chat. The game operates normally without opting in.
- Opt-in requires a private creator-only key, not merely the 8-digit room identifier or 4-letter invitation code.
- Opt-in returns a high-entropy deletion receipt. The player should copy it. The experiment page has a deletion form for past transcripts. Receipt tokens are stored in Postgres as SHA-256 digests, never raw.
- Joining a room through the invite code disables transcript collection and purges prior shared messages before the join is accepted. Multiplayer transcript collection is not supported.
- Potential emails, phone numbers and HTTP URLs are redacted before persistence. This **does not guarantee anonymity**: a reviewer must check for names, addresses and secrets before any export or training.
- Transcript deletion leaves the anonymous structured counters and rating; this distinction must be clear to participants. There is no public read/export API.
- DB failures cannot break gameplay; however, experimental feedback returns an honest 503 rather than saying feedback was durably saved when it wasn't. Consent also fails closed.

## Connect the free database — one-time owner dashboard step

The connected Render app doesn't reveal database credentials, so the connection cannot safely be completed through the current plugin.

1. Open the Postgres dashboard, choose **Connect**, and copy its **Internal Database URL**. (Keep it private.)
2. In the Render preview web service, open **Environment** and set:
   - `DARK_STORIES_PLAYTEST_DB_URL` to the internal URL
   - `DARK_STORIES_PLAYTEST_ENABLED` to `true`
3. Save; let Render redeploy the preview service. Never paste the URL into a chat or commit it to the repository.
4. Open `https://dark-stories-preview.onrender.com/api/playtest/status`; it should return `{"enabled":true}`. If it is false, the connection isn't configured.
5. Open an **experimental** case. The consent checkbox is unchecked. Submit a rating after solving/revealing. Opt in in a separate round and confirm a deletion receipt can be copied and used from the experiment page.
6. For database-level verification without exposing personal data, use Render Postgres' restricted query tool to inspect **counts only** in `ds_playtest_sessions` / `ds_playtest_transcript`. Do **not** export actual player text to the chat, GitHub issues, or Actions logs.

## Database and testing

- Schema lives in `backend/playtest_store.py`, initialized lazily on first experimental session. Uses parameterized psycopg SQL and separate consent/transcript tables.
- The test suite has mocked-route tests for opt-out, opt-in, creator-only key, deletion, multiplayer purging, legacy-case compatibility, duplicate feedback, and redaction.
- `tools/verify_playtest_postgres.py` is a disposable local/Postgres CI smoke. CI uses `postgres:16`, with artificial text only.
- `tools/export_playtest_review.py` creates a new mode-0600, owner-side JSONL file of opted-in redacted turns **requiring human approval** before any training. No public export endpoint exists.

## Retention and lifecycle

- Unconsented structured sessions: target retention **90 days**, or sooner if the free pilot DB expires.
- Opt-in transcript rows: target retention **30 days**, or sooner if free DB expires.
- `PlaytestStore` performs bounded cleanup lazily when new experimental sessions are started (at most once per hour). **This is not a hard wall-clock guarantee without a scheduled purge job.** Before expanding beyond this preview pilot, configure a daily purge in a managed scheduled environment and verify expired records are removed on time.
- Free Render database has **no backup**; upgrading or attaching backups requires separate approval. At expiry, the data may be inaccessible or deleted. Export only reviewed, consented material when appropriate and do not present this pilot as production-durable.
- App game rooms remain process-local; this project doesn't yet fix cross-instance room continuity during deployments.

## Future training path

1. Aggregate rating/solve patterns for case quality.
2. Have authorized reviewers label consented transcripts: true Yes/No, justified AlmostSolved, complete Solved, false No, spoiler, etc.
3. Filter PII again. Split by session and case. Preserve a frozen hold-out regression set (including the double-counted survivor mistake).
4. Evaluate prompt and model updates before any training. **Do not automatically fine-tune on raw moderator responses**, which include the exact mistakes being corrected.
5. Confirm current fine-tuning availability and provider-specific data-use terms before uploading any dataset.

No background harvesting, raw transcript collection, or production database changes are activated by adding the source files alone.
