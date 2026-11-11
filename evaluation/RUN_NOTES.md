# Dark Stories moderator model evaluation

**Scope:** Fixed offline question/solution benchmark on previously established cases ms-001 through ms-003. Do not confuse it with full end-to-end multiplayer or conversation-memory testing.

**Samples:** 61 human-labeled prompts (43 question answers, 18 private final-solution decisions), evaluated on GPT-4.1 mini, GPT-6 Luna, GPT-6.1 Terra, and GPT-6.1 Sol. Evaluation uses the same prompt and structured response format for all models, independent of production. The source task includes secret facts but no personal user data.

**Reproduce without cost:** `python evaluation/run_moderator_eval.py`. Dry run is the default.

**Paid execution:** The opt-in workflow only executes on a specially tagged commit or manual workflow dispatch, and only if the repository has a dedicated `DARK_STORIES_EVAL_OPENAI_API_KEY` secret (mapped to `OPENAI_API_KEY` within this isolated GitHub Action only). `python evaluation/run_moderator_eval.py --execute --budget-usd 5` enforces a maximum configured USD 5 reservation for a run; actual costs are estimated from returned token usage and standard prices as of November 10, 2026. Model access and regional charges can change.

**Output:** An aggregate JSON summary with per-model question and solution accuracy, input/output tokens, status/error counts, failed case IDs, approximate billed spend, and elapsed time. No raw LLM output or token is stored in the artifact. A result with status other than `complete` must **not** be presented as a winner.

**Limits:** This bench tests model semantic judgments under a common clean prompt. It does not test production app prompts, multi-turn game context, platform latency at scale, spoiler moderation in the live game, or private-guess correctness under real traffic. Select candidate(s) for a follow-on end-to-end pilot rather than immediately changing production.

**Setup:** Create a separate OpenAI API project and its own key with a small project spend limit, then add it as `DARK_STORIES_EVAL_OPENAI_API_KEY` under repository Settings > Secrets and variables > Actions > New repository secret. Do not paste the key into issues, PRs, chat, or code. The paid workflow can be retriggered on a new push whose commit message contains `[run-paid-eval]`.
