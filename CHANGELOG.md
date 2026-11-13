# Changelog

## v0.1.0 - 2026-11-13
Foundation and tenancy.

- Django skeleton, `/healthz`, Docker Compose (PostgreSQL 16, migration job, app, Caddy).
- Separate owner and non-owner app database roles; row-level security forced on every tenant table, fail-closed, set per request transaction.
- Accounts: login, logout, password reset, 10+ character Argon2 passwords, lockout, 30 minute idle sessions, CSP, HSTS and cookie flags.
- Scoped roles and a single permission service.
- Append-only, hash-chained audit log.
- `seed_demo` command, CI with PostgreSQL service and image build, MIT licence, README quickstart.

Known gaps: no platform-admin user; failed logins not audited; scope containment waits for v0.4.0. Manual tests M1 to M5 not yet independently run (see `docs/test-reports/v0.1.0.md`).
