# Product direction

## Vision

Make lateral-thinking mysteries easy to explore in a browser: players form hypotheses, learn from focused questions, and experience a satisfying explanation. AI moderation should support fair reasoning without spoiling the mystery.

## Current experience

A single player opens the page and receives an initial premise. They may select another of three mysteries or choose Random Premise, ask questions, request hints, and reveal the solution. In AI mode the moderator can recognize a solution or confirm all required facts. Offline mode is a development stub and cannot evaluate reasoning. After a game ends, Start Game creates a fresh room. Sharing uses native sharing when available or clipboard/alert fallback.

There are no accounts, saved sessions, leaderboards, content editor, or synchronized multiplayer experience. Room-code lookup exists in the API, but joining controls are commented out. The current share text says “I solved” even when the player revealed the answer; this is an existing limitation, not a product metric.

## Agreed four-phase roadmap

These phases are the agreed product direction. They describe future work, not existing functionality. The initial implementation priorities may be refined after technical assessment; see [ROADMAP.md](ROADMAP.md) for dependencies and acceptance criteria. No dates or production authorization are implied.

| Phase | Scope |
| --- | --- |
| 1. Foundation | Usage analytics for engagement, questions asked, solve rates, hints, and abandonment; in-game feedback, ratings, and issue reporting; basic admin metrics dashboard; improved progressive hints. |
| 2. Multiplayer | Shared mystery rooms with invite links; collaborative solving by multiple players; synchronized questions, AI host responses, and game state; private solution submissions. |
| 3. AI Mystery Generation | Dedicated generation agent with Story Architect → Logic Critic → Simulated Solver → Quality Evaluation pipeline; evaluation of originality, logical consistency, fairness, difficulty, and twist quality; curated library with initial human review. |
| 4. Community and Engagement | Player-submitted mysteries; AI-assisted mystery writing; community review and publication workflows; daily mysteries, themed collections, and achievements. |

## Target journeys

- **First-time player:** load a premise, understand yes/no questioning, submit a question, and understand the response. Improve guidance without requiring an account.
- **Stuck player:** request progressively useful hints, then deliberately reveal if desired. Distinguish revealing from solving in the result.
- **Returning player:** choose another mystery and start cleanly. Session recovery is a future design question; it does not exist today.
- **Feedback contributor (Phase 1 target):** rate a game or report a problem from the game interface.
- **Collaborative group (Phase 2 target):** follow an invite link, ask questions together, see synchronized host responses, and submit private solutions.
- **Curator (Phase 3 target):** review generated mysteries and their quality evaluations before library publication.
- **Community author/player (Phase 4 target):** draft a mystery with AI assistance, participate in review, and discover daily or themed play and achievements.
- **Developer/content maintainer:** start offline without credentials, inspect API behavior, and validate content before evaluating paid AI behavior separately.

## Proposed success metrics

No analytics pipeline, baseline, or numerical targets currently exists. The browser question count and backend counters are temporary state. Proposed measurements require a separately reviewed instrumentation and privacy plan:

| Metric | Proposed definition |
| --- | --- |
| Activation | Fraction of game starts followed by a successful first question response |
| Completion | Fraction of starts ending in a moderator-recognized solution; report reveals separately |
| Assistance | Hints used per ended game, separated by solved/revealed outcome |
| Abandonment | Started games with neither a solve nor reveal before an agreed inactivity cutoff; cutoff is still to be defined |
| Feedback | Ratings and issue reports per ended game; track issue categories and resolution separately |
| Reliability | Successful question responses divided by question attempts; track latency and upstream errors |
| Moderator quality | Human-reviewed correctness, premature-solve rate, and spoiler rate on a fixed evaluation set |
| Replay | Fraction of ended sessions followed by another start within the same browser visit |

Choose targets after collecting an agreed baseline. These are intended evaluation measures, not claims about current performance or tracked production data.
