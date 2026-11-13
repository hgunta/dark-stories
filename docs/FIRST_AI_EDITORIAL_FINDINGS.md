# AI Editorial Findings — First Screen (November 11, 2026)

**Sources:** one blind-premise pass and one full-story critic pass per existing expansion case using `gpt-6.1-terra`; 24 fresh pitch concepts proposed by `gpt-6-luna`. These are **machine judgments**, not human satisfaction results. They are deliberately treated as reject-or-investigate evidence, not proof.

## Existing library results

| Case | Terra score /30 | Blind first-guess risk | Critic disposition |
| --- | ---: | --- | --- |
| ms-004 | 9 | High | Retire |
| ms-005 | 12 | Medium | Rewrite |
| ms-006 | 9 | High | Retire |
| ms-007 | 10 | High | Retire |
| ms-008 | 8 | High | Rewrite |
| ms-009 | 8 | High | Retire |
| ms-010 | 8 | Medium | Rewrite |
| ms-011 | 8 | Medium | Retire |
| ms-012 | 11 | High | Rewrite |

**0 of 9 pass the proposed 24/30 model-score threshold.** These very low numbers reflect one model's editorial preference, not a reproducible psychological measure. The qualitative concerns are more important than the precise scores.

The blind solver guessed **smoke/fire** for 004, **e-book** for 006, **recording** for 008, **remote operation** for 009 and **temperature indicator** for 012 before being shown any solution. It also independently offered the *skis* mechanism (for 007) as a natural solution family, although its top answer was a different travel route.

## First slate: 24 new Luna pitches

**Approved for game: 0.** We did not substitute volume for quality. Some candidates were emotionally warm or clever on paper but their explanations relied on false or underdetermined setups.

Illustrative rejections:
- **The Last Place Setting:** Requires jurisdiction-dependent proxy-marriage law and contradicts ordinary assumptions without clues to discover the legal arrangement
- **A Funeral for Two:** Involves an implausibly staged funeral and unexplained criminal conspiracy
- **The Door That Opened Twice:** A potentially interesting visual-error seed, but the mirror and movement geometry are under-specified and may contradict the observation
- **The Cake Nobody Could Eat:** The display cake is almost a one-word reveal; the wedding guests' behavior is contrived
- **The Guest Who Wasn't Invited:** Genuine emotional potential, but the apparent paradox depends on manufactured language and the story isn't a deductive mystery yet
- **The House That Was Robbed Without a Thief:** The metaphorical "theft" is not a fair literal public premise, and hidden occupancy is contrived
- **The Empty Seat at the Wedding:** A lookalike + portrait creates a bait-and-switch rather than a satisfying causal explanation

*Potential seeds to investigate, not publish:* the visual-misperception family (#8) and personal-stakes family (#17). Neither is ready as written. More targeted, smaller premium-model batches should be screened just as ruthlessly.

## New explicit checks before editorial promotion

1. **Literal-truth audit:** Write each sentence of the public premise beside the corresponding solution fact that makes it literally true. If a sentence requires a twist on its own wording rather than a fair reinterpretation, reject.
2. **No hidden machinery requirement:** Can a reasonably curious player discover the twist without knowing device names, jurisdiction-specific law, or medical/engineering rules?
3. **One-question collapse:** Ask an independent blind solver for three first guesses. If one is the full solution, prefer replacement over padding the answer.
4. **Human payoff:** Is there something psychologically or narratively distinctive at stake? Emotion alone cannot substitute for logically interesting play.
5. **Red-team consistency:** Ask a skeptical reviewer to find contradictory geometry, timings, motives or undefined actors.
6. **Reveal satisfaction:** Test actual humans before accepting an AI score. Never auto-promote a candidate based on model praise.

## Caveats and cost

The second evaluation step completed and printed results in the one-time GitHub Actions job. Artifact upload failed because the upload action did not include dot-prefixed files; the result was nevertheless captured in the workflow logs. Future artifact uploads must use `include-hidden-files: true`.

The configured per-run maximum was an **estimated budget reservation** of $1.00 (Sol/Luna generation stage $0.60; Terra review $0.40), not an observed invoice. Check actual OpenAI dashboard usage for billed amounts.

**Recommendation:** Replace the shallow pack rather than merge previous difficulty PR #27. Keep production and preview content unchanged while vetting finalists.
