# Mystery Factory — writer and adversarial verifier

This is an opt-in, **draft-only** content experiment. It is NOT a
self-publishing bot. New mysteries must be reviewed by the owner and tested
in the actual game before being moved to backend/mysteries/.

## The roles

1. **Writer:** drafts one case in the existing schema, chosen from a rotating
   theme, avoiding published titles and known twists.
2. **Skeptical verifier:** independently examines the premise, causal story,
   hidden assumptions, spoiler safety, logical consistency and originality.
   It writes three expected yes/no question scenarios, a wrong near-miss
   solution, and specific feedback for the writer.
3. **Simulated moderator:** gets each proposed question and near-miss guess
   separately. Its answer is compared against the verifier's expectation.
   These are four extra live model probes per review round, **not** a
   substitute for live HTTP gameplay against the actual production prompt.
4. **One bounded revision:** If the schema, verifier or probe comparison
   fails, the writer receives the feedback and makes at most ONE revision;
   the verifier can run again.
5. **Human gate:** Output is always a candidate JSON plus a verification
   report in \`candidates/\`, never the playable \`backend/mysteries/\`.
   The only two states are \`needs_revision\` and
   \`ready_for_human_review\`, not "approved to publish".

## Run locally without spending money

\`\`\`sh
python tools/mystery_factory.py --dry-run
\`\`\`

This only prints the planned topic, existing case count and call budget.

To run a **paid** preview intentionally after approving cost, export an
OpenAI API key into your own shell/session (never commit the key), then:

\`\`\`sh
python tools/mystery_factory.py --api --run-id test-first-run
\`\`\`

The key is used only on that invocation. Requires an installed OpenAI Python
SDK (\`pip install -r backend/requirements.txt\`). At most **12 individual
model requests** can be made per invocation; some attempts may fail and
still count. Call count is NOT a guaranteed dollar budget: token counts,
model pricing, and billable errors vary. Configure OpenAI API project
budgets/alerts separately before use. Model defaults to \`gpt-4.1-mini\`
to match the current game backend; test and tune it before scheduling.

Candidate files such as \`candidates/test-first-run.json\` and the
corresponding \`.report.json\` are separate from the game's published
content directory. They contain unreleased solutions, so don't upload
them to public destinations unless you're comfortable exposing spoilers.

## GitHub Actions: weekly, OFF until you explicitly enable it

\`.github/workflows/mystery-factory.yml\` provides:
- A free manual \`workflow_dispatch\` preview (defaults to dry-run).
- A weekly scheduled trigger on **Sunday at 15:00 UTC** (not the user's
  local time). Cron scheduling is best effort, not guaranteed exact minute.
- A paid run that is skipped unless **both** the repository Actions
  configuration variable \`ENABLE_MYSTERY_FACTORY\` is set to the string
  \`true\` and the secret \`OPENAI_API_KEY\` is configured.
- A fresh branch with one candidate and its feedback report, opened
  as a **draft** pull request. Review PRs are not automatically merged.

**No schedule is enabled by adding the workflow alone.** The weekly job
exists as a disabled trigger until you set the opt-in variable. Enabling
it will authorize recurring paid OpenAI requests. I have not done that.

To activate only after reviewing and approving a pilot:
1. In GitHub repository **Settings → Secrets and variables → Actions**,
   create the secret \`OPENAI_API_KEY\` and repository variable
   \`ENABLE_MYSTERY_FACTORY=true\`. Prefer a limited-use project API key
   with a conservative spending limit and alerts.
2. Check **Settings → Actions → General** permits GitHub Actions to
   create pull requests. Repository/organization policy may disable it.
3. Use **Actions → Mystery Factory (opt-in) → Run workflow**. Choose
   \`execute=false\` first for a free dry run. Only choose \`true\` after
   approving the paid pilot. After enabling, the weekly trigger can run
   without another chat confirmation.
4. To pause the paid agent immediately, set
   \`ENABLE_MYSTERY_FACTORY=false\` or remove the secret. Existing draft
   PRs remain for review.

**Important GitHub visibility:** A draft PR does NOT make the candidate
private. If your GitHub repo is public, its proposed mystery and solution
will be readable to anyone viewing that PR. For genuinely confidential
unreleased puzzles, use a private repository/artifact workflow instead.
No credentials are stored in generated reports.

## What the verifier does NOT establish

- Three questions and one wrong guess per round are a **small adversarial
  sample**, not full game simulation. The simulated moderator does not use
  the app's actual moderation prompt or test its live HTTP solve logic.
- Multiple LLM judges can agree and still be wrong. The evaluator does
  not certify originality or legal ownership.
- Reports may be low-quality, hallucinated, or inconsistent; their statuses
  are recommendations only. A human must review the premise, inspect all
  hidden facts, check alternative plausible interpretations, and run a
  real game with 10–15 test questions and valid/invalid guesses.
- Candidate IDs can overlap between runs; don't put drafts in the playable
  directory or merge generator PRs as a substitute for editorial approval.
- The script has no unattended permission to merge, deploy, change Render,
  activate analytics or publish content.

## Review checklist / next iteration

Start with **one** manually triggered paid candidate, inspect its report,
make improvements to both prompts, and compare the candidate against an
experienced player. Only after several successful pilots should we enable
weekly generation. A later phase can add richer simulated-player traces,
deterministic regression questions per puzzle, reviewer disagreement rates
and a promotion script gated on approved reviews.
