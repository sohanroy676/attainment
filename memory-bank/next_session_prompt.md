# Next session prompt

Paste this at the start of the next Claude Code session:

> Continue Attainment: build **v0.9.0 (department, batch and quality loop)**. Read `CLAUDE.md` and the memory bank first (`progress.md`, `activeContext.md`). Do not read all of `ROADMAP.md`: only the v0.9.0 section and the design sections it names.
>
> **State.** Branch `feature/v0.8.0-workflow` holds v0.8.0, built and verified (398 passed, 15 skipped for missing golden data; ruff, mypy and `makemigrations --check` clean). Create `feature/v0.9.0-quality` from it. Earlier stacked branches (v0.2.0 to v0.8.0) are local; check `git branch -r` to see what is on GitHub. Do not tag, push or open PRs without the owner's approval.
>
> **Open from v0.8.0 (record, do not build unless v0.9.0 needs it):** HoD's department-scoped audit viewer (the viewer is college-wide only); `SupportGrant` is not enforced (no platform-admin role yet); the "overridden" marker on result pages (M3); email reminders are out of scope.
>
> **Still open from earlier versions:** Jspreadsheet paste grid and Playwright test (v0.6.0 A11), DS-A importer counts (v0.6.0 A10), DS-E published methods (v0.3.0 A10), real-data golden tests (DS-A and DS-B files are absent; if `engine/tests/golden/ds_a/course.json` exists, run `uv run pytest -m golden` first and add the v0.7.0 A1 DS-A test). Release gates for v0.2.0 to v0.8.0 are owed (golden data, manual tests, push, PRs, tags).
>
> **Rules.** All calculation lives in `engine/` (no Django, Decimal only, explicit rounding); golden tests never edited to pass; every new table gets RLS (`tenant_rls` in its migration) and an isolation test; modules call each other only through `services.py`; no real student data in git; audit logs refer to people by id only (`audit_exclude`). Scope-sensitive permission checks pass the scope (`has_permission(user, perm, "offering", id)`): an unscoped check only matches a college-wide role.

## Environment notes
- Engine tests need no database. Django tests need PostgreSQL. The owner creates `.env` (`uv run python scripts/init_env.py`; my file tools cannot touch `.env*`). Last session had no `.env`: it wrote `uv run python scripts/init_env.py --output <scratch>/test.env`, then ran `set -a; . <scratch>/test.env; set +a; docker compose -p attainmenttest --env-file <scratch>/test.env up -d db`. A new project name (`attainmenttest`) was used because the old `attainment` volume holds different passwords; the old volume was left untouched and its container stopped.
- Memory: a full test run plus Docker can exhaust RAM on this machine. Run one pytest at a time, in the background (the full suite takes about 8 minutes), and avoid parallel agents.
- Bash heredocs with quotes and `sed` with nested quotes often fail to parse here: use the Write tool for files and short Python snippets for edits.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy engine`, `uv run python manage.py makemigrations --check` before each commit. Ruff line length 100.
- Do not chain `sleep` in Bash; use Monitor or background runs.
- GitHub user: sohanroy676. CI runs only on pushes to `main`, PRs to `main`, or `gh workflow run ci.yml --ref <branch>`.
- Test patterns: `committed_db` for tests needing real commits (HTTP flows); `make_results_env` builds a full synthetic course; `apps/workflow/tests/helpers.py` adds coordinator and principal (`make_wf_env`, `submit_all`, `accept_all`, `reviewed`, `approved`, `signed`). Do not use bare `.first()` on UUID-keyed rows to pick "a" record in a test: the order is random.
