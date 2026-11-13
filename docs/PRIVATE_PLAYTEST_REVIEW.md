# Private Playtest Review — Preview

This dashboard is deployed only to the Dark Stories **Render preview branch**, never `main` or the production service. It allows the owner to inspect **explicitly consented** experimental play sessions, manually correct moderator labels and download reviewed examples. It does **not** expose a general player-transcript API.

## Access control

- URL: `https://dark-stories-preview.onrender.com/review/`
- User: `reviewer` (Render environment variable `DARK_STORIES_REVIEW_USER`).
- Password: a securely generated value stored only in the preview Render environment variable `DARK_STORIES_REVIEW_PASSWORD`. If you own the Render service, retrieve it by viewing/revealing the value in [Render preview → Environment](https://dashboard.render.com/web/srv-dbpo3tajnfac73bskjj0), or replace it with your own new high-entropy password and save/deploy.
- Authentication: HTTP Basic over HTTPS with constant-time comparison. The portal is **disabled** (404) if no user is supplied or the password is shorter than 32 characters. Every HTML, script, stylesheet, dashboard API and export endpoint requires the same credentials. No user text or credentials appear in browser URLs.
- The browser intentionally may cache Basic authentication for its session. Use a private browser window on a shared computer; close it when finished. To revoke access, rotate the password in Render.
- Writes require exact preview Origin, JSON Content-Type and a special header. There is no public annotation endpoint and no CORS permission. Responses prohibit cache storage, referrer leakage and framing.
- **Do not share credentials or downloaded reviewer exports.** A password protects access, not the privacy of manually exported files.

## What it shows

- Started games, solve rate (solves per all starts, not a completion-only metric), average rating, number of consented shared sessions and reviewed turns.
- Latest 40 sessions that still have recorded text and an active consent row.
- Each session's case ID and revision, rating, outcome, question, actual displayed moderator answer, hints, reveals and their order.
- Correct label selection (Yes, No, Irrelevant, Unknown, AskYesNo, AlmostSolved, Solved) and issue reason (correct, false negative, false positive, incorrect Yes/No, unfair solution, spoiler, unclear story, other).
- Export `dark-stories-reviewed.jsonl` containing **only human-labeled turns** with the current consent intact. Export excludes session UUIDs, marks every example `approved_for_training: false` and does **not** start training or bill any API usage.

## Privacy lifecycle

- Without opt-in, no player or moderator text enters the playtest database. With opt-in, only future messages can be captured; consent is not retroactive.
- The transcript exists only while consent remains active. Using a deletion receipt removes the transcript **and its annotations** via cascading PostgreSQL foreign keys. A session missing active consent is invisible to the reviewer and export.
- A previously downloaded human-review export is outside the database and cannot be automatically recalled on consent revocation. Before wider testing, make this limitation explicit in the participant consent notice and determine a manual export-deletion process.
- The transcript data pipeline masks common email addresses, phone numbers and URLs, but this cannot guarantee removal of all identifying details. Human review must inspect any example before further usage.
- No free-text reviewer notes are stored, only controlled correction labels.

## Daily retention

Neon Function `playtestpurge`, attached to Neon project `orange-surf-25188586`, branch `production`, is triggered daily at **03:17 UTC** through `dark-stories-daily-purge`. It does the following independently of game requests:

```sql
DELETE FROM ds_playtest_transcript
 WHERE recorded_at < now() - interval '30 days';

DELETE FROM ds_playtest_sessions
 WHERE created_at < now() - interval '90 days';
```

The function rejects public attempts to invoke it and accepts only Neon's trigger-invocation header and matching schedule payload. The proxy strips user-provided `x-neon-*` headers. Each scheduled execution uses the injected Neon `DATABASE_URL`; credentials stay off GitHub and logs.

**Verification:** temporary every-minute scheduling deleted a seeded 32-day-old synthetic transcript and 100-day-old synthetic session while preserving the recent session. The trigger was then changed to `17 3 * * *` (daily); the remaining synthetic session was deleted. Automated JS tests check trigger authentication and both SQL statements. This is a verified scheduler path, not just lazy deletion on game starts.

**Operational caveat:** database recovery snapshots / backups may retain deleted rows for a limited period under Neon's platform retention. Review those policies before broader public data collection.

## Tests and limits

- `tests/test_private_review_dashboard.py`: unauthorized access, disabled portal, secret-free responses, CSRF protection, consent revocation and JSONL export.
- `tools/verify_private_review_postgres.py`: disposable real Postgres consent/annotation/export/deletion test.
- `tools/test_retention_function.mjs`: Node tests of trigger-only invocation, SQL restrictions and rejection of forged payload.
- `npm run build`: Neon config type-check, JS retention tests, Python compile and full pytest. 834 Python and 3 JS tests passed in staging.
- **Current live data:** earlier synthetic integration tests deleted their transcript text. An empty reviewer dashboard is expected until a player shares a session.
- The dashboard is for one owner, not a team-based multiuser review service. For multiple reviewers, replace Basic auth with independent identities, MFA, audit logging and separate least-privilege database roles.
- Real-time multiplayer room continuity remains process-local and is out of scope.
