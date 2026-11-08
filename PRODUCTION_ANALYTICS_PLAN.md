# Safe production analytics launch plan (DS-009A)

**Not ready to activate.** Keep collection disabled until the four increments and owner gates below are complete. Start with backend-only counts and private owner reports; defer replay, abandonment, and hosted admin access. This plan does not authorize settings changes, storage provisioning, collection, or deployment.

## Verified facts versus missing evidence

Inspected `main` at `628b19de9b9e1a778de44d2a61631bede77ecc72`, including [ANALYTICS.md](ANALYTICS.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [DEPLOYMENT.md](DEPLOYMENT.md).

| Verified repository fact | Launch consequence |
| --- | --- |
| [Schema](backend/analytics.py) has strict v1 property allowlists, UUIDv4/UTC validation, and a 4 KiB bound. | Good minimization foundation; not consent, provenance, or authorization. |
| [Recorder](backend/analytics_recorder.py) defaults off and permits enabled test/local environments only. | Production/staging activation requires reviewed code; no current environment flag enables it. |
| [SQLite store](backend/analytics_storage.py) validates events, deduplicates retries, and enforces sequence/terminal uniqueness. | Local file reopen is tested; production durability, backups, retention, and deletion are not implemented. |
| Writes are synchronous under a recorder lock, with a five-second SQLite timeout; failures increment an in-memory drop counter without content logging. | Responses survive storage exceptions, but latency, partial writes, and lost events remain risks. |
| Rooms, analytics mappings, and sequence/terminal markers are process-local. | Keep one worker/instance. Adding a database does not make gameplay shared or restart-safe. |
| [Reporter](backend/analytics_reporting.py) shows samples/coverage; [dashboard](backend/analytics_dashboard.py) is unauthenticated loopback-only and rejects production/staging. Snapshot cap: 10,000 events. | No production admin dashboard. Replay/abandonment are unavailable; do not relabel production rows to bypass restrictions. |

**Owner must confirm:** Render service/plan/bill, disk eligibility/mount, database availability, region/scaling, console/SSH/export access, backup policy, auto-deploy settings, deployed commit, and live CI/service health. Record metadata only, never secret values.

**Pricing limitation:** this environment denied requests to official Render/Neon/Turso pricing and Render storage/backup pages (`403 Forbidden`); alternate documentation paths were unavailable. No current dollar prices, free allowances, or account entitlements were verified. Owner references: [Render pricing](https://render.com/pricing), [disks](https://render.com/docs/disks), [Postgres backups](https://render.com/docs/postgresql-backups), [Neon](https://neon.com/pricing), [Turso](https://turso.tech/pricing). These links are verification targets, not evidence that their contents were successfully read.

## Storage: choose by total incremental cost

| Option | Cost and operational tradeoff | Backup, portability, and deployment checks |
| --- | --- | --- |
| SQLite on a **verified Render persistent disk** | Lowest application complexity: reuse stdlib adapter. Quote disk + any web-plan upgrade + independent backup storage/transfer. Do not assume the current/free service supports disks. | Confirm runtime mount, redeploy survival, region/instance attachment, scaling and zero-downtime/restart restrictions. Single writer fits current architecture. Portable SQLite backup/export; persistent disk is not a verified backup. First candidate if already eligible and cheapest overall. |
| Managed PostgreSQL on Render | Additional service/driver/credentials, but potentially less owner-managed recovery. Quote compute, storage, transfer, backup/PITR and plan minimums; verify free-plan lifecycle if offered. | Confirm same-region/private connectivity, connection limits, maintenance, retention and actual restore access. Portable SQL/logical exports. Prefer an existing suitable DB or a better total-cost/recovery offer than SQLite. |
| Serverless managed Postgres, e.g. Neon | Potentially inexpensive at tiny traffic, but verify free/paid quotas, suspension, overage and backup costs. Requires a reviewed adapter, TLS and connection management. | External latency/outages, region and connection caps must fit the analytics wait budget. Test recovery; do not equate a free allowance with production durability. Good SQL portability. |
| Hosted SQLite-compatible service, e.g. Turso | Consider only if verified savings outweigh a new remote client/adapter/auth integration; it is not a local `sqlite3` path. | Verify write/storage limits, data region, exports and backup/restore support. More integration work than the current adapter; not the default. |
| Object storage | Useful low-volume backup/aggregate-export destination after pricing/access review. | Not a transactional event store without new machinery. Verify encryption, expiry, transfer and restore. Do not build a bucket ingestion pipeline or a new self-managed VPS for this launch. |

**Decision rule:** reuse a suitable existing durable DB; otherwise compare eligible disk-backed SQLite with managed/serverless Postgres, including plan upgrades and backup work. Owner records an incremental monthly cap and selects the smallest verified option within it. If nothing qualifies, stay disabled rather than use ephemeral SQLite. No provider, path, secret name, plan, or new service is selected here.

Size the quote using `30 × games/day × events/game × average encoded event bytes`, plus indexes, journaling, backup copies and headroom. These inputs are unknown; 4 KiB is a maximum, not an average. At 20 events/game the dashboard's current cap represents only 500 games, so retention alone will not necessarily solve reporting scale.

Propose daily consistent backups, a maximum 24-hour analytics loss, and recovery within one working day, subject to owner acceptance. Use SQLite's consistent backup operation rather than blindly copying a live file; journal/WAL state may matter. Verify restoration into an isolated target, schema/unique constraints, totals, and expired/deleted-row suppression. Provider snapshots/PITR are not accepted without an actual restore test. Encrypt/restrict backup access and record last-success time.

## Privacy gate before the first real event

Maintain the [event minimization contract](ANALYTICS.md): **no raw questions, answers/responses, hints, solutions, private facts/indices, exception prose, IPs, fingerprints, headers, or room access codes**. Keep typed IDs, catalog IDs, outcome codes, and necessary timing only. Browser visit IDs can remain null initially; no cross-device tracking is needed. Review hosting/access logs and OpenAI processing separately—analytics minimization does not remove those data flows.

- **Notice/choice:** explain purpose, fields, retention, owner contact, optional nature and separate AI processing. Determine applicable consent/opt-out obligations; this audit establishes no legal exemption. Conservative default: no optional collection before affirmative choice, equally accessible decline/withdrawal, and no gameplay penalty. Any different basis requires a documented owner/legal determination.
- **Page-load trap:** the UI automatically creates a room. Do not capture that game before permission or backfill it later. Permission applies to the next new game; withdrawal stops all new events immediately, including existing-room actions. A global enable flag alone is insufficient: enforce the choice server-side. Review a minimal short-lived preference mechanism without adding a tracking ID merely to store preferences.
- **Retention:** proposed 30 days for detailed events, mappings and dedupe keys; up to 90 days for genuinely anonymous aggregates only if implemented. Clean expired detail at startup before capture and on a tested independent maintenance tick, at least daily while running—not just on game requests. If hosting sleeps, verify a mechanism meeting the deletion bound or stay off. No scheduler service is authorized here.
- **Reset/delete:** use a short-lived possession capability separate from public event IDs. Stop tracking immediately; logically delete linked records within 24 hours, retire mappings, and use minimal expiring suppression metadata so retries/restores cannot recreate them. Do not infer identity from IPs or rebuild deleted starts. Explain lost-token/cross-device limitations and automatic expiry.
- **Copies:** cover owned exports, mappings and restore workflows. SQLite DELETE does not promise immediate erasure from free pages, journals or backups. Verify encryption and appropriate maintenance. Proposed backups expire within 30 days, permitting restricted copies up to roughly 60 days from event creation; disclose/approve this exception or require a shorter all-copy policy. Reapply TTL and targeted suppression before restored data becomes usable. Anonymous aggregates may not support individual retraction; document that boundary.

These controls are not implemented. Test choice/reset across questions, hints, solves, reveals and errors. Never use analytics IDs for gameplay or admin authorization.

## Deployment, activation, and rollback

Follow [DEPLOYMENT.md](DEPLOYMENT.md). Future production activation must be explicit and default off. Validate the selected durable target/mount; never silently initialize a file on an ephemeral fallback path. Missing configuration or unavailable storage disables capture **without preventing gameplay startup**. Add staging/production support deliberately; it is rejected today.

Keep one worker/instance and no development reload. Neither SQLite uniqueness nor Postgres fixes room/recorder recovery or gameplay races. Confirm current settings and auto-deploy behavior rather than replacing them from this plan.

Before launch, replace long analytics waits with a small bounded write/lock budget and fail-open circuit breaker/drop policy. The existing five-second timeout plus recorder lock can stall other requests. Expose non-content health/drop counters to the owner; never log inputs or exception diagnostics. Avoid unbounded queues/brokers. Accept and report lost/partial events: there is no crash-atomic transaction with game state.

**Staging acceptance:** synthetic data, reviewed SHA, isolated credentials, restart/redeploy persistence, consent/deletion/TTL fake-clock tests, restore verification, duplicate/terminal conflicts, full-disk/lock/network outages, bounded latency and kill-switch behavior. Record actual runtime/storage metadata without values. Live AI testing needs separate authorization; normal tests mock it.

**Manual launch:** owner approves storage cost, privacy/recovery evidence, CI/staging results, specific release and separate settings changes. Merge must not auto-deploy past that approval gate. Keep minimal backend metrics; do not claim replay/abandonment. Store database/backup credentials securely outside Git/CI; prefer least privilege and private/TLS connectivity where supported. SQLite needs restrictive file/backup access, not a new shared password.

**Rollback:** use the reviewed kill switch first; verify no new rows and working gameplay, without deleting storage or changing AI mode. An approved code rollback restores the last healthy deployment, not necessarily settings, schema, data or rooms. Keep migrations backward compatible; never auto-drop/downgrade tables. Continue retention/deletion while capture is off. Restore backups only for actual loss/corruption, apply suppression/expiry before use, and rotate compromised credentials separately. This PR performs none of these actions.

## One-owner access: private aggregate export first

Add a reviewed offline aggregate-export command executed through **verified owner-authenticated** provider console/SSH/database-client access. Require MFA on the owner account, restrict execution/transfer, export counts rather than raw event IDs/database files, and expire local copies within policy. If secure access is unavailable on the selected plan, reporting remains blocked until an approved path exists.

Current tools cannot perform this production workflow unchanged: the dashboard accepts only test/local. Do not relabel production data, change its bind, reverse proxy/tunnel it, or publish its endpoints. The output can be inspected locally; a later offline aggregate viewer must not add production HTTP routes. Recovery backups are separate restricted artifacts, not routine admin exports.

If hosted access eventually becomes necessary, use an existing trusted owner-only identity/MFA access layer with verified server-side authorization. Do not build accounts/roles or buy an identity service for the initial one-owner workflow. An obscure URL or an unverified proxy in front of the current unauthenticated app is not authentication.

## Next four focused implementation PRs

Proposed scopes only; no provisioning/deployment authorization. Preserve disabled startup through PRs 1–3. Split an item further if needed; do not silently omit acceptance criteria.

| PR | Dependencies | Acceptance criteria |
| --- | --- | --- |
| 1. Notice and collection permission | Owner-approved purpose/legal approach. | Visible notice/decline/withdrawal; no capture or backfill before choice; choice applies to next game; withdrawal stops every hook. Test forged/missing/expired permission, unchanged gameplay and disabled startup. Define the reset capability contract. |
| 2. Retention, authorized deletion and recovery tools | PR 1; approved retention/recovery targets. | Fake-clock tests for 30-day expiry, startup/periodic cleanup, 24-hour logical deletion, retry suppression and lost tokens. Test consistent backup/restore, expiry/suppression before restored data is usable, and documented copy limits. Synthetic fixtures; no public data API or provider provisioning. |
| 3. Private report/export at realistic volume | PR 2; owner-confirmed authenticated execution/transfer path. | Read-only explicit production-cohort aggregate export with sample/quality warnings, no IDs/content/path disclosure. Handle over 10,000 rows through bounded tested aggregation/scoping, never truncation. Compare with pure reporter fixtures; verify permissions/output expiry guidance. Existing dashboard stays loopback/test-local only. |
| 4. Selected durable adapter and guarded activation | PRs 1–3; verified cost/mount-or-DB/backup decision and separate settings approval. | Default off; missing mount/DB/permission disables capture, not gameplay. Add bounded waits, kill switch/circuit-breaker health and safe drop counters. Reuse SQLite or justify a Postgres driver with equivalent contract tests. Prove authorized staging persistence/recovery/privacy/reporting and disabled rollback before a later manual production release. No public dashboard. |

**Owner gate:** confirm service identity/plan, incremental budget and eligible storage, backup/export access and copy lifetime, privacy/legal choice, and release/rollback ownership. Until those facts and tests are recorded, production analytics stays off. No services, dependencies, settings, real-data collection, merge, or deployment are introduced by this plan.
