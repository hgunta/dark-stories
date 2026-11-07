# Roadmap and initial backlog

The four phases below are the agreed product roadmap. DS-001–DS-010 are the initial proposed implementation priorities approved for documentation; they may be refined after technical assessment. Dependencies and acceptance criteria below are planning recommendations for review. Future capabilities are not implemented by this documentation PR, and no dates or production authorization are implied.

## Phase 1 — Foundation

- Usage analytics: engagement, questions asked, solve rates, hints, and abandonment.
- In-game feedback, ratings, and issue reporting.
- Basic admin metrics dashboard.
- Improved progressive hints.

The initial backlog below focuses on this phase and the engineering prerequisites needed to support it. No later phase is claimed complete by these items.

| ID | Priority | Work | Dependencies | Acceptance criteria |
| --- | --- | --- | --- | --- |
| DS-001 | P0 | Project documentation | None | README, PRODUCT, ROADMAP, ARCHITECTURE, and AGENTS exist; technical claims match source; local setup is exercised; links and documentation-only diff checked; unverified assumptions reported in PR. |
| DS-002 | P0 | Automated test foundation | DS-001 | Establish pytest with API tests and mocked AI decisions; cover room creation/join, unknown rooms, hints/exhaustion, reveal/game-over, and solve decisions; document a command that executes assertions without live credentials. No test dependencies are added by DS-001. |
| DS-003 | P0 | CI pipeline | DS-002 | GitHub Actions validates pull requests by running the documented test suite on an agreed Python version; failures block a successful check; no deployment or secrets required for offline tests. |
| DS-004 | P0 | Deployment safety | DS-001; DS-003 before release validation | Verify and record actual Render settings without exposing credentials; define staging validation, rollback, and explicit human release approval. Configuration changes require separate approval; this documentation task does not change Render settings or deploy. |
| DS-005 | P1 | Usage event schema | DS-001, DS-002 | Define sessions, questions, hints, solves, reveals, and abandonment events; distinguish solved from revealed outcomes; document identifiers, payloads, timestamps, duplicate handling, and inactivity rules; review privacy and retention assumptions. |
| DS-006 | P1 | Analytics persistence | DS-005 | Select minimal durable event storage after technical assessment; events survive restart; tests cover recording, retrieval, duplicate handling, and storage failure behavior; document retention and any migration/configuration needs. No database choice is implied here. |
| DS-007 | P1 | In-game feedback | DS-002, DS-005, DS-006 | Players can submit ratings and issue reports linked to the relevant mystery/session; validate inputs, provide success/failure feedback, and persist submissions; tests cover submission and failure paths. |
| DS-008 | P1 | Admin dashboard | DS-006, DS-007 | Show engagement, question counts, solve rates, hint usage, abandonment, and feedback with documented definitions; verify aggregates against fixtures; restrict admin access using a separately reviewed approach. |
| DS-009 | P1 | Progressive hints | DS-002 | Review hint quality and ordering; define escalation that supports reasoning before revealing; test sequence, exhaustion, and per-room isolation; any later mystery-content changes are separately reviewed. Existing mysteries remain unchanged in DS-001. |
| DS-010 | P1 | Reliability | DS-002; coordinate DS-005 event semantics | Define API/upstream error responses, rate limiting, and room cleanup behavior; test failures, limits, expiry, and active-room behavior; communicate recoverable errors to players; document operational settings without changing production automatically. |

## Phase 2 — Multiplayer

Target: shared mystery rooms with invite links, collaborative solving, synchronized questions/AI host responses/game state, and private solution submissions.

Planning dependencies: the tested baseline (DS-002/DS-003), release safeguards (DS-004), and reliability work (DS-010). A separate design must address shared state, participant identity, concurrency, and the visibility of private submissions; the current room-code endpoint is not synchronized multiplayer.

Phase acceptance: multiple browser clients join the same invited room, observe consistent ordered public game activity and state, submit solutions privately under an agreed visibility policy, and recover from disconnects without contradictory outcomes. Automated multi-client tests must verify synchronization and privacy boundaries. Detailed implementation tickets are not yet assigned.

## Phase 3 — AI Mystery Generation

Target: a dedicated mystery-generation agent and multistage pipeline:

**Story Architect → Logic Critic → Simulated Solver → Quality Evaluation**

Evaluate originality, logical consistency, fairness, difficulty, and twist quality. Build a curated mystery library with initial human review.

Planning dependencies: the test/CI foundation and release safeguards, plus an agreed content schema, evaluation rubric, credential handling, and cost limits. This can be designed independently of multiplayer; no strict dependency on Phase 2 is assumed.

Phase acceptance: each candidate passes through all four stages with recorded outcomes for all five quality dimensions; rejected candidates are withheld; initial human review is required before curated publication; fixtures exercise acceptance/rejection and pipeline failures. No generation agent or pipeline exists today, and implementation tickets remain to be defined.

## Phase 4 — Community and Engagement

Target: player-submitted mysteries, AI-assisted mystery writing, community review and publication workflows, daily mysteries, themed collections, and achievements.

Planning dependencies: curated content/evaluation foundations from Phase 3, reviewed identity/permission and moderation designs, and durable data/reliable service foundations. Exact storage and community policy choices remain open.

Phase acceptance: authors can submit and revise mysteries, reviewers can approve/reject through a controlled workflow, and only approved content is published; daily/themed discovery and achievement rules have defined, tested behavior. Tests verify author/reviewer/public visibility boundaries. Detailed implementation tickets are not yet assigned; none of these capabilities currently exists.

## Planning and review rules

Keep PRs focused; split broad items into smaller changes as needed. All behavior changes require tests. Dependencies are recommended implementation ordering, not claims that work has shipped. See [PRODUCT.md](PRODUCT.md) for journeys and candidate metrics and [ARCHITECTURE.md](ARCHITECTURE.md) for current boundaries.

Open decisions: supported runtime/dependency versions; analytics retention, privacy, and abandonment timeout; admin/participant access controls; durable storage and synchronization designs; quality thresholds and AI budgets; verified Render/staging configuration and release ownership. Numerical product targets await an agreed baseline. Production configuration and every production release require explicit human approval.
