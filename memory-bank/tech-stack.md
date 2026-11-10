# Tech stack

Versions are pinned in `pyproject.toml` and `uv.lock` at v0.1.0. Design source: ADR 0002 and design v1.2.

## Runtime
- Python 3.12, uv, Django 5.2 LTS, PostgreSQL 16+ (RLS), HTMX 2.x
- Marks grid: Jspreadsheet CE (fallback Tabulator). Charts: Chart.js 4
- Pydantic 2 (method schema), openpyxl (Excel), defusedxml, WeasyPrint (PDF)
- django-simple-history, django-axes, django-otp (v1.1)
- Gunicorn behind Caddy, Docker + Compose

## Dev and test
- pytest, pytest-django, Hypothesis, Playwright, pytest-benchmark, pytest-cov
- ruff (lint + format), mypy (engine only)
- Markers: unit, golden, property, integration, isolation, e2e, perf, ops
- Locations: `engine/tests/`, `apps/<module>/tests/`, `tests/e2e/`
- Coverage targets: 90% `engine/`; 85% `apps/tenancy`, `apps/marks`, `apps/results`

## Commands (work from v0.1.0)
- Install: `uv sync`
- Tests: `uv run pytest` · by marker: `uv run pytest -m "unit or property"`, `-m golden`, `-m isolation`, `-m e2e`
- Lint/format/types: `uv run ruff check .` · `uv run ruff format .` · `uv run mypy engine`
- Django: `uv run python manage.py check` · `makemigrations --check` · `migrate` · `runserver`
- Containers: `docker compose up`

## Hosting (free tiers, checked 2026-11-06; re-check before deploy)
- Demo: Render free web service + Neon free PostgreSQL + nightly encrypted `pg_dump`. Anonymised data only.
- Not Render free Postgres (deleted after 30 days); not Supabase (pauses when idle).
- Real data: college self-hosts with Docker and local encrypted backups.

## Compliance notes
- DPDP Rules 2025 notified 14 Nov 2025; main duties from 14 May 2027; keep logs at least 1 year; under-18 consent unconfirmed.
