# Changelog

## Unreleased (built, not yet released; manual tests and golden data pending)

### v0.4.0 - academic structure and roster
- University, department, programme, batch, year, term, courses with several codes, course groups, offerings, sections, faculty assignment; setup through Django admin, audited.
- Students with scoped identifiers and history, batch and section memberships, enrolments; withdrawn and not-enrolled kept apart.
- Roster import (CSV and Excel, cached values only) with preview, reconciliation, row-numbered errors and all-or-nothing confirm.
- Role checks now understand containment: a department head covers the department's sections.

### v0.3.0 - engine: full pipeline and batch
- Section roll-up (pct, level, attainment stages; mean or weighted by students), CO to PO/PSO mapping, batch roll-up with count status, target revision rules and near-target warning, precision per level (truncate, round, none), marks-weighted and student-level CO aggregation, `run` for offerings and `batch` commands.
- R1 and R2 PO/PSO values and the R3 PO9 rule reproduced without private data.

### v0.2.0 - engine for one course
- Pure Decimal engine: Pydantic method schema, steps, trace, input and output hashes, `python -m engine run`. Golden R1/R2 tests wait for the DS-A fixture.

## v0.1.0 - 2026-11-13
Foundation and tenancy.

- Django skeleton, `/healthz`, Docker Compose (PostgreSQL 16, migration job, app, Caddy).
- Separate owner and non-owner app database roles; row-level security forced on every tenant table, fail-closed, set per request transaction.
- Accounts: login, logout, password reset, 10+ character Argon2 passwords, lockout, 30 minute idle sessions, CSP, HSTS and cookie flags.
- Scoped roles and a single permission service.
- Append-only, hash-chained audit log.
- `seed_demo` command, CI with PostgreSQL service and image build, MIT licence, README quickstart.

Known gaps: no platform-admin user; failed logins not audited; scope containment waits for v0.4.0. Manual tests M1 to M5 not yet independently run (see `docs/test-reports/v0.1.0.md`).
