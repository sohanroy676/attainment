# Next session prompt

Paste this at the start of the next Claude Code session:

> Start **v0.2.0 (engine for one course, direct attainment)** of Attainment.
> 1. Read `CLAUDE.md` and the memory bank. Read only the v0.2.0 section of `ROADMAP.md` (what is done, A1 to A16, M1 to M4) and the engine parts of `docs/solution-design.md` (section 6, code layout in section 17). Do not read the whole roadmap or design.
> 2. First check the state of v0.1.0: is `feature/v0.1.0-foundation` merged and tagged `v0.1.0`? If not, finish that gate first (push with my approval, watch CI with Monitor, M1 to M5). Then branch `feature/v0.2.0-engine` from `main`.
> 3. Use `/new-feature`. Scope = the v0.2.0 "What is done" list. Acceptance = its A-tests (automatic, write them) and M-tests (manual, list them for me).
> 4. Follow the hard design rules: all calculation in `engine/` with no Django imports, `Decimal` only (never float), explicit rounding mode, golden tests never edited to pass. Real workbooks only in gitignored `data/private/`; commit anonymised fixtures only. The golden numbers are R1 (course 2.18, Not attained) and R2 (course 2.32, Attained); the float trap must give CO 2.52.
> 5. `docs/prototype/` holds the throwaway validation engine; use it as a reference for the expected numbers, not as product code.
> 6. Do not push or tag without my approval. At the end update `memory-bank/progress.md` and `activeContext.md`, and rewrite this file for v0.3.0.

## Environment notes
- Engine tests need no database. The Django tests need PostgreSQL: `docker compose up -d db` and a `.env` created with `uv run python scripts/init_env.py` (I run this; the Read/Write tools cannot touch `.env*`). Docker Desktop is installed.
- `uv run mypy engine` is strict and must stay clean; ruff line length 100.
- Write files as UTF-8, LF, no BOM. For long files use the Write tool: long shell heredocs with quotes have failed to parse in this environment.
- GitHub user: sohanroy676. Check CI with Monitor on `gh run watch`, or the GitHub MCP tools if `gh` is not authenticated.
- Open decisions that do not block v0.2.0 are in `activeContext.md`.
