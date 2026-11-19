# Dark Stories — Mystery Difficulty Audit (Option B)

Editorial review of the nine expansion cases (`ms-004` through `ms-012`).
This is an **editorial assessment**, not measured player completion data.

## Difficulty bar

A satisfying mystery has a credible apparent contradiction, several discoverable facts,
and a causal connection the player has to make. A correct partial fact must receive
a truthful **Yes**, not an artificial No. Do **not** require an arbitrary minimum
question count, hide essential assumptions, or reject a genuinely complete explanation
solely to extend playtime.

A case is considered **at risk of an instant solve** when naming one concealed object
or mechanism effectively explains everything. Alternative hypotheses and red herrings
should arise naturally from the premise, not be inserted as irrelevant obstacles.

## Case-by-case audit

| Case | Initial assessment | Diagnosis | Action in this pass |
| --- | --- | --- | --- |
| ms-004 — The Photograph of Nothing | Medium-low | Smoke revealed by flash is a single familiar reveal | Retain, playtest and consider later rewrite |
| ms-005 — The Thicker Painting | Medium-low | Art swap is predictable, but backing detail adds a second inference | Retain, playtest |
| ms-006 — The Book That Never Left | Very easy | "It's an e-book" practically solves it | **Revised:** after-hours checkout plus format-grouped catalogue; medium candidate |
| ms-007 — The Footprints That Ended | Easy | Skis explain the missing return footprints in one guess | Retain as an intentional easier entry case; consider replacement if playtest fails |
| ms-008 — The Music That Continued | Easy | One guess of a recording solves it | **Revised:** acoustic player mechanism, programmed performance, independent power; medium candidate |
| ms-009 — The Ferry Without a Pilot | Very easy | "Remote control" solves the whole case | **Revised:** cable/current/angle reaction ferry; hard candidate |
| ms-010 — The Frozen Greenhouse | Medium | Sensor placement, vents and heat loss form a meaningful causal chain | Retain, strong control case |
| ms-011 — The Still Swimming Pool | Very easy | "Pump stopped" explains it immediately | **Revised:** running motor, blocked intake, stopped flow-linked dosing; medium candidate |
| ms-012 — The Red Sticker | Medium-low | Temperature label is straightforward, but contents and cold-chain implications add a step | Retain, playtest |

## Editorial safeguards for the four revised cases

- Public premise remains truthful; no missing fact is declared false solely to delay solving.
- There are at least four distinct required causal facts for each revised case.
- Acceptable solution variants include the mechanism and its consequence; synonymous
  explanations must still be treated as valid, rather than matching wording rigidly.
- Hint one redirects attention without naming the mechanism; hint two focuses on a
  physical or procedural relationship.
- Existing ids are preserved so catalog links and frontend functionality remain stable.
- Difficulty labels are hypotheses, subject to player testing.

## Playtest protocol

Run blind sessions with first-time players for all four revised cases and the
untouched medium control case `ms-010`.

Record:
1. Number of questions before the first meaningful discovery and final solve.
2. Whether someone solves with only one noun or one obvious question.
3. Whether each Yes/No judgment is factually and semantically correct.
4. Whether players can explain the **cause** after solving, without seeing the answer.
5. Whether a hint provides useful direction without revealing the mechanism.

Target a satisfying, comprehensible multi-step discovery, **not** a forced question
minimum. If a new case is too technical or requires encyclopedic knowledge, revise
or replace it rather than responding Unknown/No to reasonable player questions.

## Outstanding risks

- The moderator's real prompt and automatic required-fact completion path differ
  from the standalone model evaluation prompt, so the offline schema tests cannot
  prove the new cases feel fair in live gameplay.
- A player can still submit a complete explanation early; this is correct gameplay.
- The `ms-006` catalogue twist remains inherently easy to guess if a player
  immediately thinks of e-books. Consider replacing that scenario if blind testers
  continue to solve it instantly.
- None of these revisions are deployed to preview or production by this PR.
