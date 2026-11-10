# Next session prompt

Paste this at the start of the next Claude Code session:

> Start the implementation of Attainment with **v0.1.0 (foundation and tenancy)**.
> 1. Read `CLAUDE.md` and the memory bank. Read the v0.1.0 section of `ROADMAP.md` and section 17 (code structure) of `docs/solution-design.md`. Do not read the whole roadmap.
> 2. Use `/new-feature` on branch `feature/v0.1.0-foundation`. Scope = the v0.1.0 "What is done" list. Acceptance = its A-tests (automatic, write them) and M-tests (manual, list them for me to run).
> 3. Follow the hard design rules in `CLAUDE.md`. No time estimates. Real workbooks and student data never go in git.
> 4. Do not push without my approval. After approval, watch CI with Monitor and report every terminal state.
> 5. At the end update `memory-bank/progress.md` and `activeContext.md`, and rewrite this file for v0.2.0.

## v0.1.0 checklist (exact list is in ROADMAP.md)
- `pyproject.toml`, `uv.lock`, ruff and mypy config (mypy on `engine` only), pytest markers (`unit`, `golden`, `property`, `integration`, `isolation`, `e2e`, `perf`, `ops`)
- Exclude `docs/prototype/` from ruff and mypy: it is a throwaway validation script, not product code
- Django project in `config/` with base/dev/prod settings; `.env.example` with names only
- `Dockerfile` and `docker-compose.yml` with PostgreSQL
- `apps/tenancy`: college model, `college_id`, RLS policy, `SET LOCAL` per request (`ATOMIC_REQUESTS`), app role that is not the table owner, first isolation test
- Add a PostgreSQL service container and the docker build to `.github/workflows/ci.yml`; add the `docker` ecosystem to Dependabot
- MIT `LICENSE`; `CHANGELOG.md` (git-cliff) at release time; tag `v0.1.0` only after the release gate and my approval

## Environment notes
- uv should be on PATH; if not, add `~/.local/bin`.
- GitHub user: sohanroy676. `gh` may be unauthenticated in cloud sessions: check CI with the GitHub MCP actions tools.
- Write files as UTF-8 without BOM, LF endings. Use the Write tool for long multi-line files.
- Open decisions that do not block v0.1.0 are listed in `activeContext.md`.
