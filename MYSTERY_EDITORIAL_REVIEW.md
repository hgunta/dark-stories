# Mystery library editorial review — Batch 1

**Status: draft candidates, not playtest-approved.** These nine new cases are
in the library feature branch, independent of the paused Daily Challenge PR.
They have not yet passed owner approval or live AI moderator playtesting.
These cases use newly authored explanations, without claiming that no
similar puzzle has ever been published. The repository now contains 12 playable case files: three legacy
cases and nine new candidates. We are prioritizing a browsable, shareable puzzle collection rather than daily rotation.

## Quality bar before shipping a case

Have two people who haven't seen the answer play without guidance.

1. **Fairness:** Can a person deduce the explanation through yes/no questions,
   without relying on an unsupported coincidence?
2. **Internal consistency:** Do the premise, required facts, acceptable
   answers, and resolution all describe the same causal chain?
3. **Misdirection:** Is the twist surprising but natural in retrospect?
4. **Moderator behavior:** With a real configured AI client, test at least
   15 authored relevant yes/no questions per case; check correct Yes/No/
   Unknown results, no premature Solved label, no forbidden spoilers.
5. **Hint progression:** First hint changes perspective; second hint narrows
   the search but does not state the solution. Test both in the web app.
6. **Solution checking:** Test 3 valid paraphrases and 3 near-miss hypotheses,
   including an incorrect guess that contains several correct nouns.
7. **Difficulty:** Record median unassisted question count, hint use, solve
   rate and a 1–5 satisfaction rating from playtesters, if they consent.
   Do not activate production analytics just to gather these.
8. **Originality:** Manually assess whether a new story is a recognizable
   copy of a well-known puzzle. Replace it where necessary.

## Candidate review notes (spoilers)

| ID | Case | Proposed difficulty | Deductive pivot | Editorial risk to test |
| --- | --- | --- | --- | --- |
| ms-004 | The Photograph of Nothing | Medium | Flash reveals faint smoke | Is calling firefighters justified by a faint photo? |
| ms-005 | The Thicker Painting | Hard | A substitute has different frame depth | Does an observant guard notice such a small difference? |
| ms-006 | The Book That Never Left | Easy | Digital and print editions share a title | Distinguish a title-level loan record from a physical inventory record |
| ms-007 | The Footprints That Ended | Medium | Return trip leaves ski tracks, not footprints | Make sure snow conditions allow both sets of marks |
| ms-008 | The Music That Continued | Medium | Mimed performance on separately powered recording | Confirm the separate power source is plausible |
| ms-009 | The Ferry Without a Pilot | Easy | Operator controls vessel from shore | Evaluate believability of passenger ferry operations |
| ms-010 | The Frozen Greenhouse | Hard | A heat sensor incorrectly opens vents | Verify roof-vent control and thermal mechanism |
| ms-011 | The Still Swimming Pool | Medium | Still surface signals circulation failure | A calm pool alone may not prove the system failed |
| ms-012 | The Red Sticker | Easy | A color-change label flags unsafe temperature exposure | Check that the visual cue is a fair clue without being too obvious |

## Existing case cleanup

- **ms-001:** Corrected “goldish” typo and clarified the broken-bowl resolution.
- **ms-002:** Replaced a first hint that literally included a forbidden reveal
  word (“reach”). The revised first hint is less direct.

## Automation covers only the basics

`tests/test_mystery_library_quality.py` checks JSON shape, distinct IDs and
titles, required fact structure, forbidden spoiler tokens in public premise
and hints, basic authored answer variants, and API playability. It does NOT
prove logical consistency, solve fairness, model output safety, originality,
or human enjoyment. Live-model testing needs credentials and an explicitly
approved test budget.

**Next content increment:** Review each story in the local Review Desk,
capture revision requests, and test real AI moderation with a small pilot.
Prioritize replacing weak cases over hitting an arbitrary library size.
Do not promise a daily release cadence or 30-day content schedule.

## Owner review in a local browser

Run `python tools/build_mystery_review.py` from the repository root and
open the generated `mystery-review.html` file. It includes all 12 cases,
hidden solution reveal, facts, hints, answer variants, spoiler terms,
editorial checks, notes, and a per-case verdict. Click **Export my reviews**
to download a JSON file with your notes; share that file to request targeted
revisions. The generated HTML contains all secrets and is gitignored.
Do not publish it or serve it over the internet.

This tool supports *human review*, not actual AI moderation testing.
For live playtesting, start the game privately with `USE_API=true` and
test the case in the normal mystery selector. Real AI sessions consume
API quota and should remain manually approved and budget-limited.
