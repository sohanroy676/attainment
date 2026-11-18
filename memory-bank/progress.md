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

- v0.1.0 merged to `main` (PR 4) and tagged `v0.1.0` on 2026-11-13 at the owner's instruction, with M1 to M5 not independently run (recorded in `docs/test-reports/v0.1.0.md`; still owed). CI green on the branch and on `main`.
- v0.2.0 engine built on `feature/v0.2.0-engine` (2026-11-13): `engine/` with Pydantic method schema, all v0.2.0 steps, trace, input and output hashes, `python -m engine run`. 71 engine tests (synthetic analogues of A4 to A16, property tests) plus 5 golden tests, 98% engine coverage, mypy strict clean. Rules guide draft in `docs/rules-guide/`.

- v0.3.0 engine built on `feature/v0.3.0-engine-batch` (2026-11-13): roll-up, PO mapping, batch, targets, per-level precision, aggregation alternatives, offering and batch CLI. 147 engine tests, 97% coverage; R1/R2 PO values and the R3 PO9 rule match without private data.
- v0.4.0 academics and roster built on `feature/v0.4.0-academics-roster` (2026-11-13): `apps/academics`, `apps/roster`, `apps/imports`, Django admin setup screens writing to the audit log, scope resolver for role containment, roster import UI. 242 tests passing, 8 golden skipped.

## In progress
- Nothing is pushed: `feature/v0.2.0-engine`, `feature/v0.3.0-engine-batch` and `feature/v0.4.0-academics-roster` are stacked local branches (each built on the previous). The owner will run all manual tests together later.
- Waiting on the owner for golden data: `scripts/build_ds_a.py` (DS-A) and `scripts/build_ds_b.py` (DS-B). Then `uv run pytest -m golden`.
- DS-E (two published methods from other colleges) is still needed for the real A10 of v0.3.0.

## Next
- Next build: v0.5.0 (outcomes, question papers, methods) on a branch from `feature/v0.4.0-academics-roster`. Release gates for v0.2.0 to v0.4.0 are owed (golden data, manual tests, push, PRs, tags). v0.7.0 is the first end-to-end slice; v1.0.0 is the prototype.
