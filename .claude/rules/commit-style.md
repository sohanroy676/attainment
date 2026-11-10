# Commit Workflow & Message Style

After implementing a feature or fix, and only after tests pass (see `testing.md`):

1. Run `git status` and `git diff` to review all changes.
2. Stage only the relevant files with `git add` (never `git add .` blindly if unrelated files changed).
3. Write a Conventional Commits style message:
    - Format: `type(scope): short summary` (summary under 50 chars, imperative mood)
    - Types: feat, fix, refactor, chore, docs, test, perf, style, ci
    - Scopes: a module (`engine`, `tenancy`, `accounts`, `roster`, `outcomes`, `assessments`, `marks`, `methodology`, `results`, `quality`, `reports`, `imports`, `audit`, `integration`) or `ci`, `deps`, `docs`
    - Add a short body (1-3 lines) explaining WHY the change was made, not just what.
    - Example: `fix(engine): truncate after the final sum, not before`
    - Example: `feat(marks): add optimistic locking to mark cells`
4. Commit the changes.
5. Do NOT run `git push` automatically — always wait for explicit user approval before pushing.
6. Never commit directly to `main`/`master` — work on a feature branch (see `git-workflow.md`).
