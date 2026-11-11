# Dark Stories: Story Quality Standard (v1)

**Status:** Editorial gate for new and rewritten mysteries. **Not** a rule to make the moderator evasive.

## North star

The player should feel: **"That sounded impossible. I asked good questions. The answer was surprising, and now it makes perfect sense."**

A good mystery is **not** one that takes a long time to solve because the twist involves obscure machinery or arbitrary missing information. The player should have fun uncovering the explanation, not struggle to learn a niche technical fact.

### Editorial scorecard (0–5 each)

| Dimension | Five means… | Reject signals |
| --- | --- | --- |
| Hook & contradiction | One short, vivid premise with a compelling apparent impossibility | Routine mishap, technical failure, or generic "someone noticed X" |
| Twist & payoff | A surprising reinterpretation that makes the *whole premise* click | A one-word object/category answer, a device specification |
| Fairness & logic | Every detail has a coherent, discoverable explanation; no omitted arbitrary premises | Magic knowledge, unnamed secret rules, coincidental assumptions |
| Questioning opportunities | Distinct, meaningful paths of Yes/No discovery | Only one obvious question; every alternate path is Unknown |
| Human interest & tone | A memorable person, stakes, or darkly comic/human twist | Generic technician/security operator/facility story |
| Originality & diversity | Different central trick from nearby cases and recognizably not a stock riddle retread | Same "sensor/power/failure" mechanism or parallel setup |

**Scoring:** 30 maximum. Candidate needs **≥24**, no individual category below **3**, and a *separately documented* consistency/fairness pass. These thresholds are internal editorial heuristics, not scientifically validated player quality scores.

**Immediate reject:** (1) premise has a logical contradiction that only the writer can resolve through retroactive facts; (2) the twist is merely "it was an e-book / remote control / recording / faulty pump"; (3) finding the hidden noun fully solves the mystery; (4) the judge must say No to a truthful partial guess; (5) using a specialist term is necessary to get anywhere; (6) solution depends on stereotypes or harmful misinformation.

## From idea to published mystery

1. **Generate a broad slate (20–30) — not a first draft library.** Demand contrasting mechanisms: misread identity, scale, timing, unexpected motive, physical causality, perspective, mistaken assumptions, and ordinary-object reinterpretation. Cap gadget/IT/sensor based cases at 10% of the slate.
2. **Blind premise filter.** Two independent reviewers see only the title and public premise. Each writes their top three likely answers and asks whether the setup genuinely invites investigation. Eliminate contradictions with a one-question stock answer or boring stakes.
3. **Full-case editorial critique.** A critic sees solution, required facts, and hints; scores all six dimensions, identifies accidental spoilers, arbitrary assumptions, and a minimal one-question solve. A second critic acts as adversarial editor; disagreements are recorded rather than averaged away.
4. **Simulated blind player tests.** Give *only* the premise to 3 distinct player personas (novice, experienced riddle solver, skeptic). Obtain their first three likely mechanisms, plausible Yes/No questions, and an attempt at an explanation. Do not show them the answer before this step. If a substantial fraction guesses the trick immediately, reject or rewrite the premise. This is screening, not proof of real-player difficulty.
5. **Canonical truth-table and fairness cases.** For each surviving mystery, author true partial questions, false questions, ambiguous questions, near-solves, and complete explanations. Evaluate the **actual game moderator prompt** and gameplay route. True partial guesses must be Yes; invalid guesses must not be Solved; accidental wording must not force false answers.
6. **Human blind playtest.** At least **5 first-time sessions per candidate**. Track case-completion rate, number of *meaningful* discoveries, false moderator judgments, unsolicited hints, time-to-solve, and a 1–5 "satisfying reveal" vote. Player feedback beats LLM-based scoring.
7. **Ship only with evidence.** Promote at most 2–3 candidates at a time, keep a control mystery, and review feedback after 10+ completed plays. Reject mediocre cases; no requirement to keep all twelve slots populated.

### Suggested acceptance targets (to validate after data collection)

- Median player reveal satisfaction **≥4/5** over 5 blind humans.
- **0** unfair moderator denials of a clearly true clue, **0** unintended spoilers or false wins in curated stress tests.
- **≥4/5** testers agree the explanation is fair and makes sense, *even if they didn't solve it*.
- A case can be solved on question 1 if the player truly deduces it; **never** block the correct answer merely to hit a question-count target.
- If **≥2/5** blind players name the whole mechanism after reading only the premise, review the premise or reject the case.
- Never use median turns alone as a success metric.

## Token budget and spending

- Paid AI critiques are opt-in and cannot be triggered by opening a PR or deploying Render.
- Default local review uses **no API calls**.
- A paid batch requires an explicit `--execute`, a user-supplied spending cap, and configured price-per-million-token inputs, so the runner can stop before reaching the cap.
- Budget has upper-bound protections on output tokens and conservative input-token planning, but the script's **estimated dollars are not a billing guarantee**. Verify real pricing and dashboard usage before and after a run.
- Start with **$2 maximum per batch** of candidate critique + blind-probe calls. Review what was learned before buying further runs.
- The game runtime's OpenAI API key should **not** be embedded in repo files, logs, prompts, or test artifacts.

## Separation of concerns

**Mystery design** decides whether a case is worth playing. **Moderator quality** decides whether its questions are judged fairly. They must be evaluated separately. A new moderator model will not turn an uninteresting story into an interesting one.

New content remains on an isolated editorial branch until editorial review, human playtesting, and an explicitly approved merge/deployment.
