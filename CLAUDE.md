# CLAUDE.md

Attainment: a free, configurable web app that automates OBE CO/PO attainment for any college. Lecturers only enter marks; everything else is calculated, explainable and audited.

Stack: Python 3.12, uv, Django 5.2 LTS, PostgreSQL 16+ (RLS), HTMX, Pydantic 2, Decimal engine, pytest + Hypothesis + Playwright, ruff, mypy.

## Session context
@memory-bank/projectBrief.md
@memory-bank/activeContext.md
@memory-bank/progress.md

Read on demand: `memory-bank/architecture.md` (modules, calculation flow), `memory-bank/tech-stack.md` (commands, test locations), `memory-bank/systemPatterns.md`, `ROADMAP.md` (versions, tests, reference results), `docs/solution-design.md` (full design; code layout in section 17), `docs/project-statement-final.md` (requirements), `docs/adr/` (decision records).

## Status
Scaffold only: no application code yet. Next is v0.1.0 in `ROADMAP.md`. Folders in `architecture.md` may not exist; check first. The commands below start working in v0.1.0.

## Commands
- Install: `uv sync`
- Tests: `uv run pytest` (by marker: `uv run pytest -m "unit or property"`, `-m golden`, `-m isolation`)
- Lint/format/types: `uv run ruff check .` · `uv run ruff format .` · `uv run mypy engine`
- Django: `uv run python manage.py check` · `makemigrations --check` · `runserver`
- Containers: `docker compose up`
- Full list: `memory-bank/tech-stack.md`

## Hard design rules (do not violate)
- All calculation lives in `engine/` (pure Python, no Django imports). Use `Decimal` only, never float. Always set the rounding mode explicitly.
- Nothing calculated is typed in. Levels, counts and attainment are computed; changes go through override records with a reason, before approval only.
- Marks are stored per question part. Blank, 0 and absent are different states. Missing data blocks by default.
- Every tenant table has `college_id` plus PostgreSQL RLS (`SET LOCAL` per request transaction). Every new table gets an isolation test.
- Signed runs and published method versions are immutable.
- Methods are versioned JSON built from the step catalogue. No free-text formulas, no per-college code.
- Modules call each other only through `services.py`.
- Golden tests are never edited to pass; changing one needs a written reason and a MINOR bump.
- Real workbooks and student data never go in git: only in gitignored `data/private/`. Committed fixtures are anonymised.
- Secrets only in `.env`. No paid services; the app must work offline.

## Workflow
Rules live in `.claude/rules/` (security, testing, commit style, self-review, git workflow, session efficiency) and load automatically. Slash commands: `/new-feature`, `/debug`, `/commit` (in `.claude/commands/`). Work on feature branches, never commit to `main`, never push without approval. A release follows the gate in `ROADMAP.md` section 2.3. At the end of a session update `memory-bank/progress.md` and `activeContext.md`.

## Background tasks: use Monitor
Never poll or sleep-and-check background work (dev servers, long test runs, CI).
- One completion event: `Bash` with `run_in_background`, using a command that exits when done.
- A stream of events: the `Monitor` tool with a line-buffered filter that covers failure as well as success, e.g. `grep -E --line-buffered "Traceback|Error|FAILED|Killed|passed|done"`. Silence is not success.
- CI after a push: Monitor `gh run watch` / `gh pr checks` (poll >= 30s), or the GitHub MCP actions tools if `gh` is not authenticated. Report every terminal state; do not report CI green without having seen it.
- Give each monitor a specific `description`; stop finished ones with `TaskStop`.
