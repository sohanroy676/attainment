---
description: Implement a feature end-to-end on a branch with tests, review and commit
argument-hint: <feature description>
---

# /new-feature $ARGUMENTS

1. Find the feature in `ROADMAP.md`. Its version's "What is done" is the scope and its A-tests and M-tests are the acceptance criteria. Restate them (inputs/outputs, edge cases, what "done" looks like) before writing code. If the request is vague or belongs to a later version, ask first.
2. Check `memory-bank/architecture.md` and `memory-bank/systemPatterns.md` for conventions, and the relevant ADRs in `docs/adr/`.
3. Create a feature branch (`.claude/rules/git-workflow.md`).
4. Implement with minimal, targeted changes. Write the version's listed tests first where practical.
5. Write/update tests per `.claude/rules/testing.md` (including isolation tests for any new tenant table or page) and run the full suite.
6. Run `uv run ruff check . && uv run mypy engine` and `uv run ruff format .`; fix all warnings.
7. Self-review per `.claude/rules/code-quality-review.md`.
8. Commit per `.claude/rules/commit-style.md`.
9. Update `memory-bank/progress.md` and `activeContext.md`, and tick the item in `ROADMAP.md`. Record a new ADR if a hard-to-reverse decision was made.
10. Summarize the change in plain English and note it's ready for review/merge (do not push or merge without approval).
