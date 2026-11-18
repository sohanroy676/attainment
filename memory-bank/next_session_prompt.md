# Next session prompt

Paste this at the start of the next Claude Code session:

> Continue Attainment: build **v0.10.0 (reports and exports)**. Read `CLAUDE.md` and the memory bank first (`progress.md`, `activeContext.md`). Do not read all of `ROADMAP.md`: only the v0.10.0 section (about line 540) and the design sections it names (reports, section 12 of the project statement).
>
> **State.** Branch `feature/v0.9.0-quality` (from `feature/v0.8.0-workflow`) holds v0.9.0, built and verified: batch roll-up, batch page, batch sign-off and freeze, earlier-batch comparison, gap view, quality loop, plus the A11 speed test and the A12 isolation sweep. Create `feature/v0.10.0-reports` from it. All stacked branches (v0.2.0 to v0.9.0) are local; check `git branch -r` to see what is on GitHub. Do not tag, push or open PRs without the owner's approval.
>
> **For reports.** The Action Taken Report is v0.10.0 work: it reads `apps/quality` (`previous_plans`, actions taken, evidence) and the course result. Data for the reports comes through `results.services` (`present`, `present_batch`, `course_gaps`, `batch_gaps`, `comparison_columns`) and `quality.services`; do no calculation in report code (comparisons and rankings live in `engine/compare.py` and `engine/gaps.py`). Provisional results are watermarked; every report footer carries college, programme, batch, course, term, method version, engine version, run id, data status, time and content hash.
>
> **Open from v0.9.0 (record, do not build unless v0.10.0 needs it):** target-revision proposal (needs the mentor's rule); course-level CO comparison against old workbooks; batch sign-off tasks in the inbox; editing of observations and plans; free-tier size of the proof-file cap (200 MB default).
>
> **Open from v0.8.0:** HoD's department-scoped audit viewer; `SupportGrant` enforcement (no platform-admin role yet); the "overridden" marker on result pages (M3); email reminders are out of scope.
>
> **Still open from earlier versions:** Jspreadsheet paste grid and Playwright test (v0.6.0 A11), DS-A importer counts (v0.6.0 A10), DS-E published methods (v0.3.0 A10), real-data golden tests (DS-A and DS-B files are absent; if `engine/tests/golden/ds_a/course.json` exists, run `uv run pytest -m golden` first and add the v0.7.0 A1 DS-A test, and the v0.9.0 A1 and A5 tests against DS-B). Release gates for v0.2.0 to v0.9.0 are owed (golden data, manual tests, push, PRs, tags).
>
> **Rules.** All calculation lives in `engine/` (no Django, Decimal only, explicit rounding); golden tests never edited to pass; every new table gets RLS (`tenant_rls` in its migration) and an isolation test; modules call each other only through `services.py`; no real student data in git; audit logs refer to people by id only (`audit_exclude`). Scope-sensitive permission checks pass the scope (`has_permission(user, perm, "offering", id)`): an unscoped check only matches a college-wide role, and a section-scoped lecturer needs the section fallback in `quality.services._may`. No push or tag without the owner's approval.

## Environment notes
- Engine tests need no database. Django tests need PostgreSQL. The owner creates `.env` (`uv run python scripts/init_env.py`; my file tools cannot touch `.env*`). Last sessions had no `.env`: write `uv run python scripts/init_env.py --output <scratch>/test.env`, then `set -a; . <scratch>/test.env; set +a; docker compose -p attainmenttest --env-file <scratch>/test.env up -d db`. The project name `attainmenttest` is used because the old `attainment` volume holds different passwords; that volume was left untouched and its container stopped. The scratch env file is per session: if it is gone, make a new one and a new project name (or ask the owner before removing a volume).
- Memory: a full test run plus Docker can exhaust RAM on this machine. Run one pytest at a time, in the background (the full suite takes about 9 minutes), and avoid parallel agents.
- Bash heredocs with quotes and `sed` with nested quotes often fail to parse here: use the Write tool for files and short Python snippets (written to a file) for edits.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy engine`, `uv run python manage.py makemigrations --check` before each commit. Ruff line length 100. Run `ruff format` before `ruff check` (a quiet `--fix` pass prints line-length errors that the formatter then fixes). Generated migrations need `tenant_rls(...)` lines added by hand.
- Do not chain `sleep` in Bash; use Monitor or background runs.
- GitHub user: sohanroy676. CI runs only on pushes to `main`, PRs to `main`, or `gh workflow run ci.yml --ref <branch>`.
- Test patterns: `committed_db` for tests needing real commits (HTTP flows); `make_results_env` builds a full synthetic course; `apps/workflow/tests/helpers.py` adds coordinator and principal (`make_wf_env`, `submit_all`, `accept_all`, `reviewed`, `approved`, `signed`). Do not use bare `.first()` on UUID-keyed rows to pick "a" record in a test: the order is random. The synthetic course's hand-worked values: course 2.92, CO1 2.84, INT1 part 1a passed by 6 of 7 students.
