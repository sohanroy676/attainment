# Changelog

## Unreleased (built, not yet released; manual tests and golden data pending)

### v0.7.0 - results and explanations (first end-to-end slice)
- Input snapshot builder from roster, marks, papers, outcomes, targets, indirect values and the method in force; calculation runs per offering and programme (latest replaces latest; snapshots kept); stored result values; checklist of what is missing; provisional versus complete.
- Course, section and programme-separated result pages, Explain panel on every number (parts, pass counts, denominators, attempt rates, small-group flags, method and engine version, input hash), indirect value entry labelled "entered, not measured", Excel export.
- Automatic recalculation after commit when marks, mapping, target, method, indirect values, approved overrides or enrolments change (one run per offering per transaction).
- Hand-computed two-section example reproduced end to end. Real R1 and R2 on screen still wait for the DS-A fixture.

### v0.6.0 - marks entry and import
- Mark rows and cells with all states (value including 0, blank, absent, withheld, exempted, not applicable, not attempted), attempts, optimistic locking by row version, append-only change history (database-enforced), reason required after submission, per-section permissions (lecturer own section, exam branch SEE only, auditor read-only).
- Server-rendered marks grid, pre-filled Excel sheet per section, marks import with preview and all-or-nothing commit (file kept), SEE script mapping and SEE import by script number with best-N warnings, file safety (uncached formulas, entity attacks, size, type).
- Engine adapter turns stored marks into engine input. Not yet: the Jspreadsheet grid with paste and its browser test (A11), and the DS-A import counts (A10).

### v0.5.0 - outcomes, question papers and methods
- Programme outcomes, versioned course definitions and COs, CO-PO grid (blank, 0, 1, 2, 3; all-or-nothing save naming bad cells), targets per offering and per outcome and batch; grid screen; CO and map import from CSV or Excel.
- Question papers (questions, parts, CO tags, choice groups with best N and best K parts), plain-word validation, pass-mark overrides that need a reason and IQAC approval before the engine sees them, copy to a new offering, paper page.
- Methods and versions (draft, active, retired) stored as the engine's JSON; the database refuses to change or delete a published version; assignment with inheritance and locks; Vasavi theory and lab templates; validated editor screens.

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
