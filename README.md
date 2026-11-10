# Attainment

A free, configurable web app that automates OBE (outcome-based education) CO/PO attainment for any college. Lecturers enter marks per roll number; the app calculates course outcomes, programme outcomes and batch roll-ups, and explains every number.

**Status: scaffold only.** There is no application code yet. See `ROADMAP.md` for the build order; v1.0.0 is the prototype.

## What it is
- Calculates CO, PO and PSO attainment from marks, using methods stored as versioned configuration (levels, thresholds, weights, tools, rounding).
- Handles gaps in roll numbers, choice questions, absent students and several departments, sections and batches.
- Keeps every result traceable, audited and frozen once approved.
- Free to run: demo on free cloud tiers; colleges self-host real data with Docker.

## What it is not
- Not an ERP or student information system. Connecting to one comes later.
- Not a place where attainment numbers are typed in.

## How it works
1. Lecturers enter marks per question part.
2. A pure Python engine (exact `Decimal` arithmetic) runs the college's method and returns results plus a trace.
3. HoD and coordinators review, approve and report.

## Planned layout
```
config/  apps/<module>/  engine/  templates/  static/  docker/  scripts/  docs/
```
Details: `memory-bank/architecture.md`.

## Docs
- `ROADMAP.md`: versions, tests and reference results
- `docs/project-statement-final.md`: requirements (v2.0)
- `docs/solution-design.md`: full design (v1.2)
- `docs/solution-options.md`: options compared
- `docs/mentor-workbook-analysis.md`: how the reference workbooks work
- `docs/prototype/`: throwaway engine used to validate the design (not the product)
- `docs/adr/`: architecture decision records
- `CLAUDE.md` and `.claude/`: instructions for Claude Code
- `memory-bank/`: project context for AI sessions

## Development
Commands start working in v0.1.0:
```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy engine
```

## Licence
MIT (to be added with v0.1.0).
