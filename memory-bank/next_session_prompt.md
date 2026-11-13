# Next session prompt

Paste this at the start of the next Claude Code session:

> Continue Attainment. Read `CLAUDE.md` and the memory bank first (`progress.md`, `activeContext.md` list every settled design choice). Do not read all of `ROADMAP.md`: only the section of the version you work on.
>
> **State.** Eight stacked local branches hold v0.1.0 (merged and tagged) and v0.2.0 to v0.7.0 (built, NOT pushed, NOT tagged): `feature/v0.2.0-engine` > `v0.3.0-engine-batch` > `v0.4.0-academics-roster` > `v0.5.0-outcomes-papers-methods` > `v0.6.0-marks` > `v0.7.0-results` (HEAD). All tests pass locally (354, 9 skipped for missing golden data). The owner runs all manual tests together later; do not ask for them.
>
> **First, check with `git log` and `git branch` that this is still the state.** Then:
> 1. If `engine/tests/golden/ds_a/course.json` or `ds_b/batch.json` now exist, run `uv run pytest -m golden` and `-k ds_a`. A failure means an engine bug, never edit a golden expectation. Also add the v0.7.0 A1 test that loads DS-A through the importers into the database and compares the course page with R1 (2.18, Not attained) and, after approving the typed Internal-II overrides, R2 (2.32, Attained). Never read `data/private/`.
> 2. Otherwise build **v0.8.0 (workflow and governance)** on a new branch from `feature/v0.7.0-results`: read only the v0.8.0 section of `ROADMAP.md` and design sections 8 and 9. Scope: submit, accept or return, approve, sign; freeze and lock after approval; signed runs immutable (kept snapshot plus document hash); overrides with reason and approval before approval only; reopen with reason; audit of every step. Reuse `results.services.snapshot` for kept runs, `marks` and `assessments` status fields, and the `workflow.*`, `override.apply`, `data.reopen` permissions already in `apps/accounts/permissions.py`.
> 3. After that: v0.9.0 (department, batch and quality loop), v0.10.0 (reports and exports), v0.11.0 (hardening). Still open from earlier versions: the Jspreadsheet paste grid and its Playwright test (v0.6.0 A11), the DS-A importer counts (v0.6.0 A10), DS-E published methods (v0.3.0 A10), and the real-data golden tests.
>
> **Rules.** All calculation lives in `engine/` (no Django, Decimal only, explicit rounding); golden tests never edited to pass; every new table gets RLS (use `tenant_rls` in its migration) and is covered by the introspection test and an isolation test; modules call each other only through `services.py` (signals are the exception for results recalculation); no real student data in git; audit logs refer to people by id only (use `audit_exclude` on models). No push or tag without the owner's approval. At the end update `progress.md`, `activeContext.md`, `CHANGELOG.md` and rewrite this file.

## Environment notes
- Engine tests need no database. Django tests need PostgreSQL: `docker compose up -d db` and a `.env` from `uv run python scripts/init_env.py` (the owner creates `.env`; my file tools cannot touch `.env*`). In this environment a throwaway env file in the scratchpad was used and sourced with `set -a; . file; set +a`.
- A full `uv run pytest` takes about 3 minutes. Run focused paths while iterating (`apps/<module>`, `engine`).
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy engine`, `uv run python manage.py makemigrations --check` before each commit. Ruff line length 100; long divider comments are normalised by a small script (see git history) because the formatter does not touch comments.
- Write files as UTF-8, LF. Long shell heredocs with quotes often fail to parse here: use the Write tool for files and short Python snippets for edits. A multi-edit Python patch aborts on the first mismatch: check what applied.
- Do not chain `sleep` in Bash; use Monitor, `gh pr checks --watch`, or background runs.
- GitHub user: sohanroy676, `gh` authenticated. CI runs only on pushes to `main`, PRs to `main`, or `gh workflow run ci.yml --ref <branch>`. When pushing the stacked branches, push in order and open one PR per branch against the previous branch (or merge in order); CI needs the PostgreSQL service already configured.
- Test patterns: `committed_db` fixture for tests that need real commits (on_commit hooks, HTTP flows); `make_env` (marks tests) and `make_results_env` (results tests) build full synthetic courses; `bulk_create` bypasses `save()`, so pass `college_id` explicitly.
