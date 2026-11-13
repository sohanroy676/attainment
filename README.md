# Attainment

A free, configurable web app that automates OBE (outcome-based education) CO/PO attainment for any college. Lecturers enter marks per roll number; the app calculates course outcomes, programme outcomes and batch roll-ups, and explains every number.

**Status: v0.1.0 (foundation and tenancy).** You can start the app, log in as demo users of two isolated colleges and nothing else yet: marks, the engine and results arrive in later versions. See `ROADMAP.md` for the build order; v1.0.0 is the prototype.

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

## Quickstart (Docker)
Needs Docker with Compose, and [uv](https://docs.astral.sh/uv/) for the first step. Nothing else is installed on your machine; PostgreSQL runs in a container.
```
uv run python scripts/init_env.py        # creates .env with random secrets
docker compose up --build -d             # PostgreSQL 16, migrations, app, Caddy
docker compose exec app python manage.py seed_demo
```
`seed_demo` creates two demo colleges (A and B), one account per role in each (`a.admin`, `a.iqac`, `a.hod`, `a.coordinator`, `a.lecturer`, `a.exam`, `a.principal`, `a.auditor`, and the same with `b.`), and prints the password once. Set `DEMO_PASSWORD` in `.env` to choose your own.

Open <http://localhost/> and log in. Health check: <http://localhost/healthz>. Password-reset mails are printed in the app log: `docker compose logs app`.

Ports used: 80 and 443 (Caddy) and 5432 (PostgreSQL, bound to 127.0.0.1 only). If one is taken, change the mapping in `docker-compose.yml` (and `DB_PORT` in `.env` for PostgreSQL).

For a real server with a domain, set `SITE_ADDRESS=your.domain`, `DJANGO_ALLOWED_HOSTS=your.domain` and `ALLOW_INSECURE_HTTP=false`; Caddy then gets a certificate automatically.

## Layout
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
Start only the database, then run the tools from your machine (the settings read `.env`):
```
docker compose up -d db
uv sync
uv run pytest                                  # tests connect as the non-owner app role
uv run ruff check . && uv run ruff format --check .
uv run mypy engine
uv run python manage.py migrate --database owner   # migrations use the owner role
uv run python manage.py runserver
```
The test run creates and drops its own `attainment_test` database.

## Licence
MIT, see `LICENSE`.
