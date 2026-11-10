# ADR-0002: Modular monolith with a pure calculation engine

## Status
Accepted

## Date
2026-11-10

## Context
Small team (3-5 Python developers), zero budget, colleges that self-host. Results must be explainable and testable without a database or web server.

## Decision
- One Django 5.2 LTS application, split into modules (tenancy, accounts, academics, roster, outcomes, assessments, marks, methodology, results, quality, reports, imports, audit, integration). Modules call each other only through `services.py`.
- All calculation lives in a pure Python package `engine/` with no Django imports: input snapshot in, results plus a trace out.
- PostgreSQL 16+, HTMX for the UI, Docker for deployment.

## Alternatives considered
- Microservices: too much operations work for colleges to self-host.
- FastAPI + SPA: more code and a build chain; Django gives auth, admin, migrations and forms.
- Calculation inside Django models/views: cannot be tested against the mentor workbooks in isolation.

## Consequences
- Engine tests run fast and need no database.
- Module boundaries need discipline (checked in review, later by an import linter).
- One deployable unit.
