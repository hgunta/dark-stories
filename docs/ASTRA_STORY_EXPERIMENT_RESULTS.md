# Astra Story Experiment — Editorial Review (November 11, 2026)

**Status:** COMPLETED, NOT APPROVED FOR GAME. No merge or deployment.
Runs:
- [First six, reasoning exhaustion](https://github.com/hgunta/dark-stories/actions/runs/43120419738)
- [Five complete Astra drafts + Sol critique](https://github.com/hgunta/dark-stories/actions/runs/43121847779)
- [Three revised Astra stories + new Sol critique](https://github.com/hgunta/dark-stories/actions/runs/43123323908)

## Outcome

The initial six Astra requests were all marked **incomplete**: medium reasoning exhausted 4,100 output tokens each, with no readable story. Background polling fixed the original HTTP timeout, but did not fix insufficient output allowance.

The second, lower-reasoning attempt produced five complete stories. Each received an independent, adversarial `gpt-6.1-sol` critique. The best three underwent one additional substantive Astra revision each, then another Sol review.

| Original | Initial Sol /30 | Revised title | Revised Sol /30 | Decision |
| --- | ---: | --- | ---: | --- |
| The Second Rescue | 20 | Room for Two | 18 | **Hold original only for discussion; do not publish** |
| Something to Hold | 18 | The Only Person He Wouldn't Hurt | 14 | **Hold original only for discussion; do not publish** |
| The Spare Child | 16 | The Uninvited Witness | 16 | **Hold original only for discussion; do not publish** |
| The Brother She Could Buy Back | 15 | — | — | Reject |
| The Perfect Pupil | 14 | — | — | Reject |

**0/5 originals and 0/3 rewrites cleared the 24/30 model-quality gate**. The model review is not human playtest evidence.

## Provisional top three for owner review — no approvals

**The Second Rescue:** Two witnesses seem to disagree over whether a mother threw her boy to a rescuer or to a drowning man. In the full explanation she threw him toward his drowning father to force the boatman to turn back. **Weakness:** the two witness descriptions are not actually incompatible, and the physical rescue sequence needs work.

**Something to Hold:** A scrap in a murdered woman's hand exactly matches the hem of her daughter's doll dress, although the dress was sewn after her death. The victim had torn fabric from the husband's shirt during the murder; afterward, he made the doll dress from the shirt, leaving the matching edge. **Weakness:** the fabric-reuse answer is a simple first guess, and the father retaining incriminating fabric is contrived.

**The Spare Child:** An orphan deliberately steals a visiting couple's purse, happy when her younger brother is taken home; she later learns he was already chosen. She tried to make herself unadoptable so he would get the one available place, but the couple initially intended to adopt both and rejected her after the theft. **Weakness:** the ending assumes an implausibly harsh and unexplained about-face by the adopters.

The rewritten variants attempted to repair these flaws but made the central mechanisms even more immediately guessable. Their scores fell or remained unchanged. The originals are **not** strong enough to replace the current cases.

## Recorded token-based cost estimates

Using standard API input/output rates (Astra $10/$50 per million, Sol $2/$10 per million), and the model's logged token usage:

- Six incomplete Astra generations: **$1.25943**
- Five Astra drafts + Sol critiques: **$0.984146**
- Three Astra revisions + Sol re-critiques: **$0.397044**
- **Estimated total: $2.64062 of the authorized $5**; remaining estimated allocation $2.35938.

These are *token-based estimates*, not verified invoices or a provider-enforced monetary ceiling. Actual charges should be confirmed in the API dashboard.

## What we learned

1. **Strong models do not create story quality on their own.** A model can produce internally detailed narratives with obvious one-guess reveals.
2. **Adding causality and human drama is necessary but not sufficient.** A premise must withhold the mechanism *fairly* while inviting several interesting lines of questions.
3. **Revisions can decrease surprise.** The initial five received higher average editorial scores than their rewrites, even when the rewrites were more coherent.
4. **Do not force publication of top three merely because they outrank poor alternatives.** Human blind playtests and literal-truth checks remain required.
5. **Next method:** Human editor should commission more specific story seeds drawn from genuinely paradoxical human behavior, and select by *premise-first blind deduction* before paying for expanded plots. Short concise proposals before full manuscripts are likely to be more cost effective.

## Separation from game

This PR changes **only offline editorial scripts, tests, and documentation**. Playable mystery JSON and production / Render preview remain unchanged. Draft results exist in short-retention GitHub Actions artifacts and logs; never automatically copy them into the library.
