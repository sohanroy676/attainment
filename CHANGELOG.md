# Changelog

## Unreleased (built, not yet released; manual tests and golden data pending)

### v0.11.0 - hardening, privacy and operations (built, not yet released)
- Security: decompression-bomb guard on every Excel upload; per-user rate limits on PDF rendering, uploads and the full export; `verify_audit` command (every college, non-zero exit on a broken chain); `create_college` command; dependency audit in CI; `docs/security-review.md`.
- Isolation sweep: every record endpoint found in the URL configuration is requested with GET and POST as six users of another college.
- Privacy (`apps/privacy`): retention list, notice, then anonymising of name and identifiers after the notice period (marks stay; stored upload files purged; audit chain stays valid); per-student data export (audited); `anonymise_roster` for fixtures and demo data; `RetentionNotice` table with RLS.
- Operations: encrypted backup and restore scripts, scheduled restore test, `update.sh` with rollback, `docker-compose.prod.yml` (no published database port, read-only app, log rotation, public or internal HTTPS, `ops` profile with the superuser login).
- Performance: the marks grid loaded rows, cells and roll numbers per student (2.4 s for 130 x 30); now bulk-loaded. Performance tests for the grid and the result pages.
- Accessibility: a script scans the key pages; fixed unlabelled mark cells and reason boxes and report pages without a main area.
- Fix: an error inside `college_context` was hidden by a second error while restoring the college.
- Documents: admin guide, user guide, known limits, privacy notice template, test report with what was not run.
- Not done: demo deployment, full update-cycle test (A9), 10-college volume test, manual tests M1 to M6.

### v0.10.0 - reports and exports (built, not yet released)
- PDF reports (WeasyPrint) from HTML templates with a footer and a provisional watermark: CO sheet per assessment, theory and lab analysis, CO-PO/PSO table, Action Taken Report, batch report with a three-batch chart, explanation appendix. Excel for the main tables, NBA course list, full college export (Excel and JSON). Per-college template override.

### v0.9.0 - department, batch and quality loop (built, not yet released)
- Batch roll-up from signed course runs per programme batch (PO and PSO direct, indirect, total, status, core and non-core counts), recording the course runs used and the ones left out; indirect values and targets per outcome; a switch to include unsigned courses (marked, provisional).
- Batch sign-off: prepared (IQAC), approved (HoD), signed (principal); the signed batch run is frozen by the database; reopening needs a reason and starts a new cycle.
- Earlier batches: PO values from an old workbook (CSV or Excel, checked whole, file kept), three-batch comparison, and a side-by-side check of computed against old values at the method's shown precision (`engine/compare.py`).
- Gap view: COs under the course target, the weakest question parts (pooled over sections), POs and PSOs under their batch target (`engine/gaps.py`).
- Quality loop: observations (drafted from the gap view), action plans that carry to the course's later offerings, actions taken with dates and proof files (PDF, PNG, JPEG, 5 MB each, checked by their bytes, per-college cap).
- Speed: a batch of 100 courses by 15 outcomes rolls up and renders in under 3 s. Isolation sweep over every new page.
- Not built: target-revision proposal, Action Taken Report (v0.10.0), course-level comparison with old workbooks, batch tasks in the inbox, editing of observations and plans.

### v0.8.0 - workflow and governance (built and verified locally)
- Fix: a department-scoped HoD can now approve a pass-mark override for their own offerings (the check was college-wide only).
- Section marks: draft, submitted, accepted or returned (reason). Course result: reviewed, approved, signed, reopened (reason, new cycle). Table-driven state machine.
- Approval locks marks (service check plus database trigger); signing seals the run (frozen by triggers, content hash); reopen unlocks and stores a new run; "differs from signed" banner.
- Overrides refused after approval. Signature records (name, role, time, hash). Support grant (time-limited, not yet enforced). Task inbox and audit viewer.

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
