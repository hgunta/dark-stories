# Editorial triage of expansion cases 004–012

**November 2026. Status: internal critique, not measured player scores.**
The existing expansion cases are **not** approved for automatic promotion merely because their JSON passes schema tests.

| Case | Call | Why it underperforms | Editorial next action |
| --- | --- | --- | --- |
| 004 · Photograph of Nothing | **Rework** | Flash exposing smoke is visually legible, but the answer is close to a one-clue observation | Keep photograph concept; introduce an honest change of interpretation, not an arbitrary extra technical dependency |
| 005 · Thicker Painting | **Rework** | Painting replaced by fake is the first guess many people will make; the thicker backing feels like forensics rather than a story | Rebuild the premise around a more surprising personal consequence; check that the frame clue is sufficient |
| 006 · Book That Never Left | **Retire** | E-book is a one-word semantic loophole. The draft v2 adds catalogue mechanics, not meaningful mystery | **Replace premise and solution entirely** |
| 007 · Footprints That Ended | **Hold as easy control** | Skis can be guessed quickly, but there is a clean, physical contradiction and a satisfying spatial explanation | Keep only if blind-player reveal satisfaction is high; do not pretend it is hard |
| 008 · Music That Continued | **Retire** | Recorded playback and separate power are obvious. The v2 automatic piano is arguably *more obscure, not more delightful* | **Replace entire story**; avoid another music-technology trick |
| 009 · Ferry Without a Pilot | **Retire** | Remote steering is an instant solve; v2 reaction ferry demands special knowledge of a niche mechanism | **Replace entire story**, avoid specialist transport engineering |
| 010 · Frozen Greenhouse | **Rework / compare** | Sensor, vent and heater chain is mechanically sound but feels like a maintenance incident | Preserve only if it works with players; compare with a more human premise |
| 011 · Still Swimming Pool | **Retire** | Pump stopped is a boring operational fault. V2 pump blockage + dosing interlock adds complexity without payoff | **Replace entire story** |
| 012 · Red Sticker | **Retire** | Temperature indicator is a compliance fact, with almost no deduction after identifying the label | **Replace entire story** |

## Implications for PR #27

Draft PR #27 (`content/mystery-difficulty-v2`) is **not recommended for merge as written**. The four rewrites address the number of required facts, not the fundamental entertainment problem. Preserve that work as an experiment and don't quietly ship it.

## Immediate slate strategy

1. Keep the three original reference cases (001–003) untouched.
2. Re-evaluate case 007 as an intentionally easy warm-up.
3. For cases 006, 008, 009, 011, 012, demand **completely different plots**.
4. For 004, 005, 010, run a side-by-side premise contest before selecting whether to rewrite or replace.
5. Run the **story quality gate** before creating playable JSON entries.

## False shortcuts

- **More hidden facts** are not necessarily more interesting.
- **More technical steps** are not necessarily harder in a fair way.
- **Making the moderator say No/Unknown** is never a valid solution to shallow content.
- **Lengthy premises** often leak the twist and reduce the hook.
- **Model scores alone** are not evidence that humans enjoy a mystery.

## Candidate concept commissioning brief

Request ideas built around one **meaningful mistaken assumption** followed by a crisp causal explanation, ideally with an emotional or darkly comic payoff. Balance the slate across:
- Who/what the player assumes is involved
- Where an event occurred versus where it appears to have occurred
- Timing and sequence
- The unintended consequence of an ordinary action
- A seemingly irrational human decision with a rational hidden motive
- Physical evidence that has been read backward

Avoid filling the slate with sensors, motors, power outages, remote controls, disguised software features, or medical protocol unless the human stakes and twist are extraordinary.

A complete candidate package contains: two-sentence public premise; exact causal solution; every hidden assumption; 4–8 truthful likely questions; three plausible wrong avenues; a blind first-guess prediction; two escalating spoiler-safe hints; and sample acceptable final explanations. Reject candidates without all of these.
