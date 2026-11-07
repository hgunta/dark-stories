# Instructions for coding agents

## Understand the existing project

Read [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PRODUCT.md](PRODUCT.md), and [ROADMAP.md](ROADMAP.md), then inspect the relevant source. Roadmap proposals are not authorization to implement future features.

Preserve the Python/FastAPI service, vanilla JavaScript frontend, and JSON mystery storage unless a concrete requirement justifies a change. Prefer simple solutions and minimal dependencies. Do not add a frontend framework, database, service, or package merely because one is familiar. Explain any justified architecture/dependency change for review.

Use the existing checkout in isolated cloud tasks; do not create a Git worktree unless explicitly requested. Preserve unrelated user changes. Check Git status before and after work. Use a feature branch when requested and keep pull requests small and focused. Describe the problem, resulting behavior, validation, and limitations. Never merge without authorization.

## Validation

Require tests for behavior changes, including regression coverage of the changed behavior. The baseline repository has no automated suite: establish appropriate focused tests when changing behavior rather than claiming nonexistent commands passed. Use mocked AI responses for deterministic tests; do not make ordinary tests depend on paid API access. Validate documentation links and commands for documentation-only work; application tests need not be added for prose changes.

Run the checks appropriate to the change and report exactly what passed, failed, or was not run. Distinguish offline stub behavior from AI moderation. Use the documented backend working directory and one worker; reload/restart clears rooms. Avoid changing tracked bytecode during checks, for example with `PYTHONDONTWRITEBYTECODE=1`.

Do not change mysteries or their private facts unless the task explicitly includes content changes. Never expose private solutions in UI or logs inadvertently. Inspect actual request/response handling before making technical claims.

## Secrets, production, and releases

Never commit secrets or credentials, including API keys, dotenv contents, tokens, or sensitive request logs. Use secure environment configuration and ignored local dotenv files. Do not print secret values or put them into fixtures, PR text, or examples. Missing credentials must be reported without inventing values.

Do not modify production configuration, including Render settings, without explicit approval. Do not deploy to production automatically. Every production release requires explicit human approval before release execution. A code review, merged PR, local smoke test, or environment setup does not by itself authorize production deployment.

Document deployment proposals separately from verified settings. No committed Render configuration currently establishes a production command. Do not infer live service health, credential validity, or persistence from local success.
