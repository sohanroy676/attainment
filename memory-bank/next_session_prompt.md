# Next session prompt

Paste this at the start of the next Claude Code session:

> Continue Attainment. First check the state of **v0.2.0 (engine for one course)**:
> 1. Read `CLAUDE.md` and the memory bank. Check `git log` and whether `feature/v0.2.0-engine` is merged and tagged `v0.2.0`.
> 2. If `engine/tests/golden/ds_a/course.json` exists, run `uv run pytest -m golden`. These are the R1 and R2 golden tests (course 2.18 Not attained, and 2.32 Attained with the typed Internal-II pass marks). If one fails, find the engine bug; never edit a golden expectation to pass. If the file does not exist, the owner still has to run `scripts/build_ds_a.py`: remind them and do not read `data/private/`.
> 3. Finish the v0.2.0 release gate in `ROADMAP.md` section 2.3 (M1 to M4 recorded in `docs/test-reports/v0.2.0.md`, changelog entry, push with approval, PR, watch CI with Monitor). Tag only with the owner's approval.
> 4. Then start **v0.3.0 (engine: full pipeline and batch)**. Read only the v0.3.0 section of `ROADMAP.md` and design sections 6.2, 6.3 and 7. Branch `feature/v0.3.0-engine-batch`. Scope: `RollUp`, `TargetCompare` extras (near-target warning), `MapToOutcomes`, batch roll-up, `BatchInput`, `CountStatus`, per-level `Precision` (question, CO, course, PO, batch; truncate, round, none), `TargetRevise`, `AggregateToCO` alternatives, and DS-B golden batch tests (R3, R4). A10 needs two published methods from other colleges (DS-E): ask the owner for them rather than inventing numbers.
> 5. Hard rules as always: all calculation in `engine/` with no Django imports, `Decimal` only, explicit rounding, golden tests never edited, no real student data in git, no push or tag without approval. At the end update `progress.md` and `activeContext.md` and rewrite this file.

## State of the engine (v0.2.0)
- `engine/`: `schema.py` (Pydantic method), `model.py`, `loader.py` (marks JSON), `pipeline.py` (`run(method, course)`), `steps/` (one file per step family), `trace.py`, `hashing.py`, `precision.py`, `__main__.py` (`python -m engine run <method> <marks> [--trace] [--json]`).
- Try it: `uv run python -m engine run docs/examples/method.json docs/examples/sample-marks.json --trace`.
- Tests: `engine/tests/` (unit, property, golden). Builders in `engine/tests/builders.py`. Coverage 98%.
- Decisions made for v0.2.0 are listed in `memory-bank/activeContext.md`; extend the method schema compatibly (`attainment-method/1`).

## Environment notes
- Engine tests need no database. Django tests need PostgreSQL: `docker compose up -d db` and a `.env` from `uv run python scripts/init_env.py`. My Read/Write tools cannot touch `.env*` files (permission rule); the owner creates `.env`. In this environment I used a throwaway env file outside the repo.
- `uv run mypy engine` is strict; ruff line length 100. Write files as UTF-8, LF. Long shell heredocs containing quotes have failed to parse here: use the Write tool for files.
- Do not chain `sleep` in Bash; use Monitor or `gh pr checks --watch`.
- GitHub user: sohanroy676, `gh` is authenticated. CI only triggers on pushes to `main` and on PRs to `main` (or `gh workflow run ci.yml --ref <branch>`).
