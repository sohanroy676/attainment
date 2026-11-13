# Progress

## Done
- Requirements: research and problem statement merged; final statement v2.0 (2026-11-06).
- Mentor workbook analysis: course (Deep Learning) and batch (CSE 2021-25) workbooks re-run through a prototype engine (`docs/prototype/`). Findings: R1 and R2 reproduce exactly; batch roll-up reproduces for all 15 outcomes; float arithmetic gives CO1 2.51 instead of 2.52, so `Decimal` is required.
- Solution options compared (stack, grid, hosting) - 2026-11-06.
- Design `solution-design.md` v1.0 to v1.2 (22 sections), two review passes, user's 12 decisions applied - 2026-11-09.
- Roadmap v0.1.0 to v1.0.0 and beyond, with automatic (A) and manual (M) tests per version - 2026-11-10.
- Repo scaffold (this commit set): `.claude/` rules, commands and settings; CI and Dependabot; ADRs 0001 to 0008; memory bank; CLAUDE.md, README.md, ROADMAP.md - 2026-11-10.
- Project documents added to `docs/` (statement, design, options, workbook analysis, prototype) - 2026-11-10.

- v0.1.0 foundation and tenancy built on `feature/v0.1.0-foundation` (2026-11-13): Django skeleton and /healthz; Dockerfile, compose (PostgreSQL 16, migrate job, app, Caddy) and role script (owner and non-owner app role); College, tenant base model and manager, FORCE RLS with fail-closed policy, SET LOCAL per request transaction; accounts (login, logout, reset, 10+ character Argon2 passwords, django-axes lockout, 30 minute idle sessions, CSP/HSTS/cookie flags); scoped roles and one permission service; append-only hash-chained audit log (trigger plus revoked grants); `seed_demo`; CI with a PostgreSQL service and docker build; MIT licence; README quickstart. 49 automatic tests green locally as the app role (A2 to A9 and the M2, M4, M5 flows).

## In progress
- v0.1.0 awaits: push and green CI (A1), the manual tests M1 to M5, the release gate and approval before tag `v0.1.0`. Nothing pushed yet.

## Next
- Finish the v0.1.0 gate, then v0.2.0 (engine, direct attainment), then follow `ROADMAP.md` in order. v0.7.0 is the first end-to-end slice; v1.0.0 is the prototype.
