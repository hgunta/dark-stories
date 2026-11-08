# Mystery library editorial review — Batch 1

**Status: draft candidates, not playtest-approved.** Each new case is original copy
written for Dark Stories, not a claim that a similar puzzle has never been
published. The repository now contains 12 playable case files: three legacy
cases and nine new candidates. A 12-day UTC rotation still repeats within
a month. Do not market this as 30 days of unique puzzles.

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
| ms-012 | The Warm Delivery | Easy | Medicine's cold chain was breached | Packaging surface warmth may not prove product temperature; consider adding an indicator |

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

**Next content increment:** review and improve these cases based on playtests,
then add 18+ more *reviewed* cases to approach a nonrepeating 30-day catalog.
When changing the catalog size, schedule publication around the UTC daily
rollover: a modulo-based daily selector can remap the current day's case if
the catalog changes mid-day. A pinned release calendar is a later improvement.
