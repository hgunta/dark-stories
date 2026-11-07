# Deployment and release runbook

## Scope and evidence

This runbook preserves the existing FastAPI service, vanilla JavaScript frontend, and JSON mysteries. It documents a manual release process; it does not configure or authorize deployment. Follow [AGENTS.md](AGENTS.md): production configuration changes require approval and every production release requires explicit human approval. A merged PR or green CI is not release approval.

| Status | Evidence or boundary |
| --- | --- |
| Verified in repository | FastAPI serves the frontend and API; dependencies are in `backend/requirements.txt`; pytest uses `requirements-test.txt` and `pytest.ini`; the [Tests workflow](.github/workflows/tests.yml) selects Python 3.12 and runs offline tests. |
| Verified in source | Rooms and codes are in process-local dictionaries; mysteries are JSON; no database or frontend build is required; AI mode requires `USE_API=true` and `OPENAI_API_KEY`. |
| Render settings verified | None. No Render dashboard configuration, deployed commit, service health, pricing, or rollback availability has been independently verified for this runbook. |
| Recommendations only | The staging layout, build/start commands, environment separation, merge safeguards, and release/rollback steps below. They are not a record of current Render or GitHub settings. |

No Render manifest or production start configuration is committed. Do not treat examples below as approved changes to the existing production service. See [ARCHITECTURE.md](ARCHITECTURE.md) for current limitations and [ROADMAP.md](ROADMAP.md) for future work.

## Local validation before a PR

From the repository root, using Python 3.12:

```bash
python3 -m venv /tmp/dark-stories-test-venv
/tmp/dark-stories-test-venv/bin/python -m pip install --no-cache-dir -r requirements-test.txt
/tmp/dark-stories-test-venv/bin/python -m pip check
env -u OPENAI_API_KEY USE_API=false PYTHONDONTWRITEBYTECODE=1 /tmp/dark-stories-test-venv/bin/python -m pytest -q -p no:cacheprovider
```

The suite uses FastAPI TestClient, mocked AI completions, isolated room dictionaries, and network guards. No running server, credential, or paid AI call is required. Passing tests include characterization of existing errors, not proof those errors are fixed. Dependencies remain unpinned, so fresh installs can resolve different versions.

For manual browser validation, use the [README local startup instructions](README.md). Confirm page load, a question, hints, reveal, and Start Game. Offline ordinary questions return `Unknown. (offline mode)`; offline mode cannot validate AI reasoning. Record test results and any unrun checks in the PR. Documentation-only changes require link/source consistency checks; new application tests are not needed for prose alone.

## GitHub CI and merge gate

The existing **Tests** workflow triggers on PRs targeting `main` and pushes to `main`. Its **pytest (Python 3.12)** job runs on GitHub-hosted Ubuntu, installs `requirements-test.txt`, runs `python -m pip check`, and executes the complete suite. It sets `USE_API=false` and `PYTHONDONTWRITEBYTECODE=1`, unsets `OPENAI_API_KEY` for pytest, and uses only `contents: read`. It has no deployment steps and needs no configured GitHub, Render, or OpenAI secrets.

Inspect results in the PR's **Checks** tab or **Actions → Tests**, including install, dependency-check, and test logs. A feature-branch push without a PR does not trigger this workflow. If no run appears, confirm the PR targets `main`, Actions is enabled, and any contribution approval has been granted. Do not claim hosted CI passed from local results alone.

Recommended manual repository safeguards: require a PR, at least one human approval, the actual **pytest (Python 3.12)** check emitted by GitHub, and checks on an up-to-date branch; disallow force pushes/deletion and limit bypasses. Verify the reported check name and available enforcement options in GitHub before configuring them. These rules are not installed by the workflow or this document, and current settings are unverified. Do not enable automatic merging as part of this process.

## Recommended staging layout

Keep the existing production service and add one separate Render Python web service for staging, only after approval to create/configure it. Use the same repository and `main`, with manual selection of the exact release candidate commit. Avoid an extra database, persistent disk, separate frontend service, or build system for the current application.

Use one instance and one worker: multiple workers/instances have independent rooms. Prefer the smallest suitable available service plan; verify current pricing, sleep behavior, and account eligibility rather than assuming a free plan exists. A Render-provided staging hostname avoids custom-domain work. Staging has no application authentication; do not assume its URL is private or safe for an unrestricted paid AI key.

The following are proposed commands for a service whose working directory is the **repository root**, with both `backend/` and `frontend/` included. They are derived from the source layout, not verified existing Render commands. Confirm Render runtime/port behavior before applying them.

Build:

```bash
python -m pip install -r backend/requirements.txt
python -m pip check
```

Start:

```bash
python -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port "$PORT" --workers 1
```

Do not use `--reload` on staging or production. Select an explicitly supported Python 3.12 patch version through Render's supported runtime configuration; no deployment version is pinned by this repository. The root requirements file uses plain Uvicorn; the backend file above includes its standard extras.

## Environment and credential separation

| Environment | Recommended application variables | Credential handling |
| --- | --- | --- |
| Local/CI validation | `USE_API=false`, `PYTHONDONTWRITEBYTECODE=1` | No API key; tests suppress dotenv loading and remove `OPENAI_API_KEY`. |
| Staging by default | `USE_API=false`, `PYTHONDONTWRITEBYTECODE=1` | Omit `OPENAI_API_KEY`. |
| Staging AI check | `USE_API=true`, `PYTHONDONTWRITEBYTECODE=1` | Separate staging key in Render's secure environment settings; deliberate authorized integration check with budget controls. |
| Production | Verify current mode first; for AI use `USE_API=true`; recommend `PYTHONDONTWRITEBYTECODE=1` | Production-only key supplied securely through Render; changes require explicit approval. |

Never put credential values in Git, examples, PRs, screenshots, test fixtures, or logs. Verify variable names/presence without displaying values. Avoid environment-group sharing that exposes production credentials to staging. Restrict dashboard access and use separate OpenAI projects/keys and budget alerts where available; application rate limiting is not currently implemented. CI must not receive production credentials.

The application calls `load_dotenv()` and ignores `.env` and `backend/.env` in Git; Render deployments should use secure service environment settings rather than committing dotenv files. Missing a key with `USE_API=true` prevents startup. The model is hardcoded to `gpt-4.1-mini`; availability, account access, and quota need a separately authorized live staging check. AI failures are not comprehensively recovered by the application.

## Manual Render verification before any release

An authorized maintainer must record non-secret findings for both services:

- Service identity/ownership, repository connection, source branch, and deployed commit.
- Root directory, build/start commands, Python version, port handling, instance count, and scaling settings.
- Auto-deploy policy and deploy hooks/integrations: ensure merging or pushing cannot bypass the manual production approval gate. If current automation would deploy on merge, resolve it with explicit configuration-change approval **before** merging a release candidate.
- Variable names/presence, environment-group scope, staging/production credential isolation, and responsible credential owner; never record values.
- Health check, hostname/custom-domain routing, plan/region, sleep behavior, access permissions, and log access.
- Availability/retention of previous deployments and the supported rollback procedure, including whether configuration changes are restored.

No dedicated health endpoint exists. Recommend `/api/mysteries` as an interim read-only probe that exercises mystery loading; separately check `/` for the frontend. Neither proves AI availability or a complete game works. Any settings correction requires its own approval and must not be silently bundled into a release.

## Development → PR → CI → staging → production

1. Develop a focused change on a feature branch, preserve unrelated work, and run the appropriate local validation. Never change gameplay or content merely to bypass tests.
2. Open a PR against `main`; require human review and successful CI. Resolve failures and record limitations. Verify production auto-deploy cannot bypass the manual gate before merging.
3. After an authorized merge, wait for CI on the resulting `main` commit. Record that exact full SHA; a passing PR merge-ref check alone does not identify the final release artifact.
4. With staging-deployment authorization, manually deploy the exact candidate SHA to staging. Do not implicitly deploy whatever commit happens to be latest. Record resolved dependency/runtime versions because they are unpinned.
5. Verify the deployed SHA and run the staging checks below. If the candidate changes, repeat CI and staging validation for the new SHA.
6. Prepare a release record: candidate SHA, CI run/result, staging evidence and mode, configuration differences, known risks, release owner, last healthy production deployment/SHA, and rollback plan. Never include secret values.
7. Obtain explicit human approval for that production release and any separate configuration changes. Confirm the intended production service and candidate before execution. A green build, merge, staging deployment, or this runbook is not approval.
8. An authorized operator manually deploys the same candidate SHA to the existing production service. Preserve its domain/service identity; do not replace it with staging. Git identity alone does not guarantee identical dependencies across unpinned rebuilds; compare runtime/dependency evidence.
9. Verify the deployed SHA, read-only frontend/catalog checks, and an approved small synthetic game check; monitor errors. Record the outcome. If unhealthy, follow rollback below. No deployment should occur automatically from this documentation task.

### Staging acceptance checks

- Verify the expected SHA, runtime, single instance/worker, and intended offline/AI mode.
- Load `/` and `/api/mysteries`; expect the interface and three mystery entries.
- Start each mystery; confirm its public premise, submit a question, request hints in order through exhaustion, reveal, and verify further messages report game over.
- Use Start Game to begin again; verify a separate room does not inherit prior hint/solve state. Room-code lookup can be checked through the API even though the join UI is disabled.
- In offline mode expect the stub response. For an authorized AI check, verify a real moderation response and solve/reveal handling using the staging key; offline CI does not verify this integration. Avoid writing private facts or credentials to shared logs.
- Check failure logs and record results without secret values. Do not promote a failed or unverified candidate.

These checks create temporary rooms, so execute them only on the authorized staging target; do not point validation scripts at production accidentally. Staging setup and verification have not been executed by this documentation change.

## Minimal production rollback

Before release, verify an accessible last-known-healthy deployment, record its commit/runtime and non-secret configuration metadata, and ensure an authorized operator can restore it. Confirm the procedure and retention in Render beforehand; this repository cannot establish rollback availability.

1. If production regresses, pause further release attempts and notify the release owner. Obtain explicit human authorization for the rollback; follow the organization’s approved incident process if one exists.
2. Select the previously healthy deployment using Render's supported rollback controls. Prefer restoring the retained artifact over rebuilding an old commit, because unpinned dependencies may resolve differently. Verify the service identity and rollback target before executing.
3. Do not assume code rollback restores environment settings or credentials. Review any configuration differences separately; restore only approved settings through secure controls. If no retained rollback target exists, stop and agree a recovery deployment plan rather than blindly rebuilding.
4. Confirm the restored deployment/SHA, frontend/catalog responses, and an authorized minimal game check. Record logs, outcome, impact, and follow-up work without credentials. Fix the regression through another reviewed PR before retrying release.

There is no database migration to reverse in the current application. Active rooms and chat are not recoverable: restarts, redeploys, and rollback lose process-local state. A persistent disk alone does not persist Python dictionaries. Communicate this limitation before releases; successful rollback restores service behavior, not previous games.
