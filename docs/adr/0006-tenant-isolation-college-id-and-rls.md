# ADR-0006: Tenant isolation with college_id and PostgreSQL row-level security

## Status
Accepted

## Date
2026-11-10

## Context
Several colleges may share one deployment (demo, later hosted). Student data must never cross colleges, even if application code has a bug.

## Decision
- Every tenant table has `college_id`.
- PostgreSQL RLS policies filter on a per-transaction setting (`SET LOCAL`, with `ATOMIC_REQUESTS`). Policies fail closed when the setting is missing.
- The app database role is not the table owner and has no BYPASSRLS.
- An isolation test suite is auto-discovered from the models, so every new table is covered.

## Alternatives considered
- Application-level filtering only: one missed filter leaks data.
- Schema or database per college: heavy migrations and operations.

## Consequences
- Every query path must run inside the request transaction; background jobs set the college explicitly.
- Tests need a real PostgreSQL (CI service container from v0.1.0).
