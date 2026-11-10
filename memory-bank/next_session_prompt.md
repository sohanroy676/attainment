# Next session prompt

Paste at the start of the next session:

> Read `CLAUDE.md` and the memory bank. Start v0.1.0 from `ROADMAP.md` using `/new-feature`, on a feature branch. Scope = the "What is done" list for v0.1.0; acceptance = its A and M tests. Do not push without approval.

## v0.1.0 checklist (see ROADMAP.md for the exact list)
- pyproject.toml, uv.lock, ruff and mypy config, pytest markers
- Django project (`config/`), settings split, `.env.example` (names only)
- Dockerfile, docker-compose.yml with PostgreSQL
- tenancy: college model, `college_id`, RLS policy, `SET LOCAL` per request, non-owner app role, first isolation test
- CI: PostgreSQL service container, docker build; Dependabot docker ecosystem
- CHANGELOG.md (git-cliff) and tag at release time

## Environment notes
- uv should be on PATH; if not, add `~/.local/bin`.
- GitHub user: sohanroy676. `gh` may be unauthenticated in cloud sessions: check CI with the GitHub MCP tools and watch with Monitor.
- Write files as UTF-8 without BOM, LF endings (a BOM can break ruff and `.env` keys).
- Use the Write tool for long multi-line files.
- At the end of the session update `progress.md` and `activeContext.md`.
