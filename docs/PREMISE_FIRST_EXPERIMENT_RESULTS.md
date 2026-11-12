# Premise-first experiment — November 11, 2026

**Outcome: seven distinct seeds, three developed mysteries, zero approved.**

This was one capped experiment on the *editorial branch only*. The underlying
GitHub Actions run completed successfully:
[Premise-first experiment](https://github.com/hgunta/dark-stories/actions/runs/43162493569).
Its draft stories and full model critiques are in the run logs and short-lived
artifact; they are **not** in the playable mystery directory.

## Premise-only slate

| # | Working title | Initial finding | Follow-up |
| -- | -- | -- | -- |
| 1 | The Walk Above the Ladder | Coherent surface-history illusion, but one-question cast/installation answer | Developed |
| 2 | The Envelope That Arrived Too Soon | Ambiguous use of “broken”; too many invented legal/repair details | Rejected |
| 3 | A Career in Other People’s Pockets | Familiar charity reauction and a direct contradiction (“every buyer gave away” includes last) | Rejected |
| 4 | The Customer Who Wanted to Be Cheated | Coherent motive but ordinary evidence-gathering story; nothing truly paradoxical beyond one question | Developed |
| 5 | The Journey Through the Wall | Coherent moving-reference-frame puzzle, but a single “did the room move?” guess | Developed |
| 6 | The Lamp in the Counting Room | Solution contradicted the assertion that money vanished **from** the room | Rejected |
| 7 | The Man Who Would Not Be Seated | Semantic dodge plus implausibly inept staff; “chairs for others” solves the setup | Rejected |

The initial Sol audit rated 1, 4 and 5 as *potential* and selected them for
Astra development. **That gate was too permissive**: each also had a documented
one-question solution, which should have disqualified it *before* paid
development. The runner has now been tightened to require explicit PASS
for three distinct premises and to stop without developing if fewer pass.

## The three developed candidates

| Result | Core mechanism | Independent Sol /25 | Decision |
| --- | --- | ---: | --- |
| **The Tracks Beneath the Stone** (from #1) | Downward-projecting “footprints” are sediment casts filling original dinosaur track depressions | 19 | REJECT |
| **No Floor Required** (from #5) | A motionless lift serves as extra turning room for a rigid trolley at a corridor junction | 16 | REJECT |
| **The Frozen Alibi** (from #4) | A coin sunk in a refrozen glass indicates a thaw/refreeze cycle, so apparently frozen food cannot be trusted | 16 | REJECT |

The independent critic found the same pattern in all three: **good physical
explanations but very weak lateral-thinking entertainment.** Each was
effectively one reveal, with its direct consequences mislabeled as multiple
independent discoveries. The frozen-coin idea is also a familiar household
test. The dinosaur example depends on geological knowledge, which conflicts
with the accessibility requirement. None has darkly interesting human stakes.

**Do not add any of these stories to the playable library.**

## What changes now

1. **Reject one-question collapse at the premise stage**, even if the mechanism
   is elegant and physically coherent. Do not reward a writer for presenting
   consequences of the same discovery as independent twists.
2. Commission mysteries with two **meaningfully separate but causally linked**
   deductions. One should revise an assumption about evidence or the scene,
   and the other should revise the meaning of a consequential human action.
   Avoid merely adding an arbitrary dark backstory.
3. An opening should support at least two productive investigative routes,
   rather than telegraphing the one necessary physical trick.
4. Independently verify literal truth and plausibility. If the intended answer
   is one of many equally likely explanations, rework or reject.
5. Only a *truly* promising premise gets a full solution, moderator goldens and
   human blind playtests. Never mark a generated story as shipped or approved
   based on model scores alone.

This experiment **did not** validate three publishable cases. The quality
standard remains intentionally higher than the best results of this run.

## Safety and scope

The runner's preflight budget used a conservative estimated reservation of
$2.15 plus ~$2.65 from the previous authorized $5 experiment. This is not a
billing guarantee or verified actual spend; inspect API usage for real costs.
No additional paid retries were launched after the review.

The branch has editorial code, documentation and tests only. Neither preview
nor production was merged or deployed.
