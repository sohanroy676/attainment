# Self-Review Before Committing

Before committing any change, re-read the diff acting as a strict code reviewer and check for:

- Security: hardcoded secrets, unsanitized input, unsafe file/shell operations, SQL built from strings, any query that skips the college filter
- Personal data: real student names or roll numbers in code, tests, fixtures, logs or docs
- Calculation: arithmetic on marks or percentages outside `engine/`, any `float` in the calculation path, rounding without an explicit mode
- Error handling: missing try/except, silent failures
- Complexity: functions doing too much, deeply nested logic, unclear naming
- Duplication: logic that already exists elsewhere in the codebase (especially calculation rules, which live only in `engine/steps/`)
- Consistency: does this match existing patterns in the project (see `memory-bank/systemPatterns.md`)?
- Dead code: unused imports, commented-out blocks, leftover debug logs/print statements

Fix anything flagged before proceeding to commit. If unsure whether something is an issue, err on the side of fixing it.

## General coding style

- Make minimal, targeted edits — do not rewrite entire files unless the task genuinely requires it.
- Do not "helpfully" refactor unrelated code while fixing a specific bug; stay scoped to the task.
- Prefer clear, boring code over clever one-liners.
- Run `uv run ruff check .`, `uv run ruff format .` and `uv run mypy engine` before committing and fix all warnings (not just errors).
