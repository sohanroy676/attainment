# Roadmap: v0.1.0 to v1.0.0 (prototype) and beyond

**Current status:** repo scaffold done (Claude files, CI, ADRs, memory bank). Next: **v0.1.0**. No application code exists yet.
**Note:** `solution-design.md` (v1.2) and `project-statement-final.md` (v2.0), cited below, are in `docs/`.

**Version 1.0 of this roadmap** · 2026-11-10 · Based on `solution-design.md` v1.2 and `project-statement-final.md` v2.0.
**No dates or durations.** Versions are released in order, each when its gate is met (section 2). The prototype is **v1.0.0**.

Contents
1. Versioning rules
2. How testing works (applies to every version)
3. Test data sets and reference results
4. Version overview
5. Versions v0.1.0 to v0.11.0 (building up to the prototype)
6. v1.0.0: the prototype release
7. After v1.0.0
8. Traceability: requirements and acceptance scenarios by version
9. Open items and when each is needed

---

## 1. Versioning rules

Format: **vMAJOR.MINOR.PATCH**.

| Part | Changes when | Example |
|---|---|---|
| MAJOR | A breaking change: data that needs a manual migration, a method-schema change with no converter, or an API break. Never used to change a signed result (signed results are never altered). | v1.x.x → v2.0.0 |
| MINOR | A new feature set, or any change to an engine rule that can change a calculated number | v0.4.0 → v0.5.0 |
| PATCH | A bug fix with no rule, schema or feature change. A regression test is written first. | v0.6.0 → v0.6.1 |

- Below v1.0.0 every MINOR is a planned build step (this roadmap). Before v1.0.0, schemas may still change between MINOR versions, but migrations must run on the previous version's demo database.
- **Engine version** is recorded in every calculation run. It follows the product version when the engine changes; a release that does not touch the engine keeps the old engine version.
- **Method schema version** (`attainment-method/1`) changes only with a MINOR or MAJOR bump, and old method versions must keep running (tested converter or reader).
- Any change to a golden test output (section 3) needs a written reason in the changelog and a MINOR bump.
- Every release has: a git tag, a changelog entry, release notes saying whether any result can change, and a test report (section 2.4).

---

## 2. How testing works (applies to every version)

### 2.1 Two kinds of tests
- **Automatic tests (A-tests):** run by CI on every push; all must pass to release. They run on synthetic or anonymised data only.
- **Manual tests (M-tests):** a person follows the steps on the demo site and records pass or fail. They are written so that someone who did not build the feature can run them.

Test IDs are written `vX.Y.Z/A3` or `vX.Y.Z/M2`. Each version's tests include all tests of earlier versions (regression); a version lists only its **new** tests.

### 2.2 Planned test layers and markers (names may change when code exists)
| Marker | What | Tool |
|---|---|---|
| `unit` | One function or step | pytest |
| `golden` | Mentor-workbook results (reference results in section 3) | pytest |
| `property` | Random inputs, rules that must always hold | Hypothesis |
| `integration` | Several modules and the database | pytest-django |
| `isolation` | One college cannot see another's data | pytest-django |
| `e2e` | A browser doing what a user does | Playwright |
| `perf` | Size and speed limits | pytest-benchmark |
| `ops` | Backup, restore, update, container | CI scripts |

Planned commands: `uv run pytest -m "unit or property"` (fast), `uv run pytest -m "not perf and not ops"` (default), `-m golden`, `-m isolation`, `-m e2e`, and `uv run pytest` (everything).

### 2.3 Release gate (every version)
1. All A-tests of this version and all earlier versions pass in CI.
2. All M-tests of this version are run by someone other than the author; result, tester and date recorded.
3. Golden outputs unchanged, or the change is written up with a reason.
4. The isolation suite passes (it grows with every new table and page).
5. Migrations run on a copy of the previous version's demo database.
6. No open defect of kind **blocker**: wrong result, data leak, or data loss.
7. Changelog, release notes and test report written; tag created.

### 2.4 Manual test report format
One file per release (`docs/test-reports/vX.Y.Z.md`) with a table: test ID, tester, date, result (pass / fail / blocked), notes, defect link.

### 2.5 Demo accounts for manual tests (created by a seed command; passwords are set at seeding)
Platform admin · College A admin · IQAC · HOD (CSE) · Coordinator (Deep Learning) · Lecturer 1 (Deep Learning, section AIML) · Lecturer 2 (another course) · Exam branch · Principal · Auditor · College B admin (second college, for isolation tests).

---

## 3. Test data sets and reference results

### 3.1 Data sets
| ID | Content | Used for |
|---|---|---|
| DS-A | Vasavi Deep Learning, CSE-AIML 2025-26 (anonymised): 67 students (roll numbers with gaps), Internal-I (14 parts), Internal-II (12 parts, "answer any 4 of 6"), quiz and assignment (3 each), lab (30 marks), SEE (25 parts, 66 students by script number), CO-PO map | Golden course tests, end-to-end tests |
| DS-B | Vasavi CSE 2021-25 batch: per-course PO/PSO values for all courses of all 8 semesters, targets, earlier-batch totals (2019-23, 2020-24) | Golden batch tests |
| DS-C | Synthetic rosters: gap list (1-4, 6-8); Section A 1-100 and B 1-89; A 1-66 and B 67-130; alphanumeric ids; the same roll number in two sections | Roster tests |
| DS-D | Synthetic edge-case marks (prototype tests T1 to T9): best 2 of 3 parts, tie at fifth place, student with four answers, mark exactly at 60%, merged level 2.5, below 10%, nobody attempted, rounding 2.845 | Engine tests |
| DS-E | Two published methods from other colleges, written as test cases (to be collected) | Scenario 16 |
| DS-F | Two synthetic colleges with overlapping roll numbers and course names | Isolation tests |

All fixtures are anonymised (roll numbers replaced, names removed) before they enter the repository.

### 3.2 Reference results

**R1: Deep Learning, decided default rules (strict 60% pass mark; choice questions count only students who attempted; compulsory count everyone who sat; truncate to 2 decimals).**

| | CO1 | CO2 | CO3 | CO4 | CO5 |
|---|---|---|---|---|---|
| Internal level | 3 | 3 | 2 | 3 | 1 |
| SEE % | 58.80 | 51.06 | 57.19 | 46.52 | 45.57 |
| SEE level | 2 | 2 | 2 | 1 | 1 |
| Quiz level / Assignment level | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 |
| Direct CO | 2.40 | 2.40 | 2.10 | 1.80 | 1.20 |
| Final CO (indirect 3) | 2.52 | 2.52 | 2.28 | 2.04 | 1.56 |

- Course attainment 2.184 → **2.18, Not attained** (target 2.2).
- PO/PSO: PO1 2.13, PO2 2.10, PO3 2.33, PO4 2.31, PO5 2.10, PSO1 2.10, PSO2 2.18, PSO3 2.18.
- Internal-I %: CO1 72.13, CO2 78.17. Internal-II %: CO3 57.94, CO4 72.19, CO5 45.97 (46.12 when "best 4 of 6" is applied; levels unchanged).
- Quiz 67 of 67 = 100% and assignment 67 of 67 = 100% (Level 3). Lab 67 of 67 at 18 or more marks (Level 3).

**R2: Deep Learning with the college's typed Internal-II pass marks entered as approved per-part overrides (2 for the 3.5-mark parts).**

| | CO1 | CO2 | CO3 | CO4 | CO5 |
|---|---|---|---|---|---|
| Internal level | 3 | 3 | 3 | 3 | 3 |
| SEE level | 2 | 2 | 2 | 1 | 1 |
| Direct CO | 2.40 | 2.40 | 2.40 | 1.80 | 1.80 |
| Final CO | 2.52 | 2.52 | 2.52 | 2.04 | 2.04 |

- Course attainment 2.328 → **2.32, Attained**.
- PO/PSO: PO1 2.29, PO2 2.28, PO3 2.41, PO4 2.38, PO5 2.31, PSO1 2.28, PSO2 2.32, PSO3 2.32 (these equal the college's report).
- Internal-II %: CO3 79.88, CO4 86.86, CO5 69.49 (69.94 with "best 4 of 6").

**R3: CSE 2021-25 batch roll-up** (simple average of course values; total = 0.8 × direct + 0.2 × indirect; indirect entered as 3).

| | Courses with a value | Direct (unrounded) | Total (unrounded) | Target | Status (compared unrounded) |
|---|---|---|---|---|---|
| PO1 | 84 | 2.7999 | 2.8399 | 2.55 | Attained |
| PO2 | 83 | 2.7628 | 2.8103 | 2.65 | Attained |
| PO9 | 19 | 2.8242 | 2.8594 | 2.86 | **Not attained** (Attained only if the total is rounded to 2.86 first) |
| PO11 | 6 | 2.7000 | 2.7600 | 2.75 | Attained |
| PO12 | 52 | 2.6998 | 2.7598 | 2.65 | Attained |
| PSO1 | 51 | 2.7863 | 2.8290 | 2.55 | Attained |

The full 15-column table is the project statement's Appendix B (batch totals as in the file). Course counts attained: CSE core 50 of 51, non-core 29 of 29; CSE-AIML core 48 of 51, non-core 28 of 29 (as typed in the file; the app must match or list each difference).

**R4: Other fixed expectations**
- Float trap: internal 3, SEE 2, quiz 3, assignment 3 → direct 2.40 → final CO **2.52** (ordinary floating-point maths gives 2.51 after truncation).
- Rounding: 2.845 rounded to 2 decimals half-up (Excel style) = **2.85** (Python's default half-even gives 2.84).
- SEE best 5: script 11 has 6 answers; Q17 (total 3) is dropped.
- Internal-II best 4 of 6: 66 students answered exactly 4; one student (roll …003) answered 5 and Q6 (total 1) is dropped.
- Boundary: a mark of exactly 1.8 out of 3 passes with `>=` and fails with `>`.

---

## 4. Version overview

| Version | Name | Main result | Status |
|---|---|---|---|
| v0.1.0 | Foundation and tenancy | Runs locally; login; two colleges kept apart | Planned |
| v0.2.0 | Engine: one course, direct attainment | Reproduces R1 and R2 up to final CO and course | Planned |
| v0.3.0 | Engine: full pipeline and batch | Reproduces R1 to R4 including PO and batch; second method as config | Planned |
| v0.4.0 | Academic structure and roster | Colleges, courses, sections, students, roster import | Planned |
| v0.5.0 | Outcomes, question papers, methods | Deep Learning fully set up; method versions | Planned |
| v0.6.0 | Marks entry and import | All Deep Learning marks loaded; grid; history | Planned |
| v0.7.0 | Results and explanations | **First end-to-end:** R1 and R2 on screen with explanations | Planned |
| v0.8.0 | Workflow and governance | Submit, approve, sign, freeze, override, reopen | Planned |
| v0.9.0 | Department, batch and quality loop | R3 on screen; action plans; gap view | Planned |
| v0.10.0 | Reports and exports | PDFs and Excel in the college's formats | Planned |
| v0.11.0 | Hardening, privacy, operations | Backups proven, security checked, demo deployed | Planned |
| **v1.0.0** | **Prototype release** | All 20 acceptance scenarios pass; demo and docs ready | Planned |
| v1.1.0 | Pilot readiness | Method wizard, dry-run diff, two-factor, reminders | Planned |
| v1.2.0 | Methods and rules from the pilot | Rule decisions applied; more methods as config | Planned |
| v1.3.0 | Indirect attainment | Surveys replace the typed indirect value | Planned |
| v1.4.0 | Integration (read) | REST API, API keys, webhooks | Planned |
| v1.5.0 | Access and reach | Single sign-on, translations, mobile marks entry | Planned |
| v2.0.0 | Multi-college operations | Onboarding automation, ERP adapters, credit-weighted roll-up | Planned |

**Order note:** v0.7.0 is the first end-to-end slice. If progress slips, stop widening and finish v0.7.0 before starting v0.8.0.

---

## 5. Versions v0.1.0 to v0.11.0

### v0.1.0: Foundation and tenancy

**Goal:** a running app skeleton where colleges are isolated by the database itself and every later feature has a safe place to live.

**What is done**
- Repository, Docker setup (app, PostgreSQL, Caddy), CI (lint, tests, image build), Django skeleton with the empty modules from design section 3.3.
- Tenant (college) model; current-college middleware; base model with `college_id` and a manager that always filters.
- PostgreSQL row-level security: `SET LOCAL` per request transaction, fail-closed policy, app role that is not the table owner.
- Users, login, logout, password reset, password rules, lockout after repeated failures.
- Roles with scope (college, department, programme, offering, section) and a single permission service.
- Append-only audit log with hash fields; login and role changes are logged.
- `/healthz`; seed command that creates two demo colleges and the demo accounts (section 2.5).

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | CI runs lint, tests and image build on push | All green |
| A2 | `docker compose up`; call `/healthz` | HTTP 200; reports database reachable and migrations current |
| A3 | Introspection: every tenant table has `college_id` and an RLS policy | Test fails if one is missing |
| A4 | Two colleges each with a sample record; query as College A through ORM, raw SQL (app role) and HTTP | Only A's rows; with no college set, zero rows |
| A5 | Two consecutive requests for different colleges on the same database connection | No setting leaks from the first to the second |
| A6 | Lecturer assigned to section X requests section Y | Denied |
| A7 | Login and role change events; try `UPDATE` and `DELETE` on audit rows as the app role | Events present; update and delete refused |
| A8 | Password of 9 characters; repeated wrong logins | Rejected; account locked after the limit |
| A9 | Response headers and cookies | Secure, HttpOnly, SameSite, HSTS, CSP present |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | On a clean machine, follow the README to start the app | Login page opens at the documented address |
| M2 | Log in as each demo role | Each reaches a home page stub; a wrong password shows a plain message |
| M3 | As College A admin, paste the address of a College B record | Not found or forbidden; no data shown |
| M4 | Reset a password (dev mail shown in the console) | New password works; old one does not |
| M5 | Leave a session idle past the timeout | Next click returns to login |

**Expected output:** a tagged build that starts with one command, two isolated demo colleges, zero cross-college rows, green CI.

---

### v0.2.0: Engine for one course, direct attainment

**Goal:** the calculation core, standing alone, reproduces the mentor's course numbers up to course attainment.

**What is done**
- Engine package with no Django imports; data classes for inputs and outputs; exact `Decimal` arithmetic; precision helper with explicit round or truncate.
- Steps: `NormaliseStates`, `ChoiceSelect`, `QuestionPass` (with per-part override), `Denominator` (`by_choice`, `attempted`, `sat`, `enrolled`, `fixed`, whole-assessment-absent rule), `AggregateToCO` (mean), `PerStudentAverage`, `SingleTotal`, `Bands` (flag and value for calculation), `MissingData`, `MergeTools` (average), `WeightedCombine`, `Average`.
- Method config as JSON, validated by a schema; pipeline built from the config; trace output for every value.
- Command-line runner: `python -m engine run <config> <marks>`.
- Anonymised DS-A as fixtures; DS-D edge cases.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | Golden R2 (typed Internal-II pass marks as overrides) | Levels, direct, final CO and course exactly as R2 (course 2.32, Attained) |
| A2 | Golden R1 (no overrides) | Exactly R1 (course 2.18, Not attained) |
| A3 | Per-question pass counts from fixtures with overrides applied | Equal the workbook's own counts (14 Internal-I, 12 Internal-II, 25 SEE columns) |
| A4 | SEE best 5 | Script 11: Q17 dropped and logged; SEE levels 2, 2, 2, 1, 1 |
| A5 | Internal-II best 4 of 6 | 66 students keep 4; the 5-answer student drops Q6; levels unchanged |
| A6 | Boundary at exactly 60% | Passes with `>=`, fails with `>` |
| A7 | Float trap case | Final CO 2.52, never 2.51 |
| A8 | Denominators | Choice question counts attempted only; compulsory counts all who sat; a student absent for the whole assessment is excluded |
| A9 | DS-D synthetic cases T1 to T3 | Q17 best 2 of 3 parts; tie goes to the lower question number; four-answer student drops nothing |
| A10 | Bands: 9.99, 10.00, 50.00, 60.00 | Flagged with no level; Level 1; Level 2; Level 3. With "block", the result is provisional |
| A11 | `MissingData`: no part tagged to a CO, or nobody attempted | Block (default); renormalise and zero options behave as documented |
| A12 | Merge of Internal-I Level 3 and Internal-II Level 2 | 2.5 |
| A13 | Quiz absent handling | `zero` lowers the average; `skip` ignores the item |
| A14 | Invalid configs: weights not summing to 1, overlapping bands, unknown tool, percent outside 0 to 100 | Rejected with a message naming the field |
| A15 | Same input twice | Identical output and identical hash |
| A16 | Import check and type check | No Django imports in the engine; type check passes |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Run the command line on DS-A with the default config and with the overrides config | Printed tables equal R1 and R2 |
| M2 | Read the trace for SEE CO2 | Shows each part, pass count, denominator, attempt rate, exclusions; understandable without help |
| M3 | Edit the config: set pass mark to 55%; then break it (weights sum 1.2) | Numbers change as expected; the invalid config is rejected naming the field |
| M4 | Mentor or IQAC reads the first draft of the rules guide | Step names and meanings accepted or corrections listed |

**Expected output:** the command line prints a per-tool and per-CO table matching R1 or R2, each with a readable trace.

---

### v0.3.0: Engine, full pipeline and batch

**Goal:** everything from course attainment to batch results is calculated by the engine, and a second college's method is expressed by configuration only.

**What is done**
- `RollUp` (section → course; stages: percentage, level, attainment), `TargetCompare` (unrounded or displayed; near-target warning), `MapToOutcomes` (weighted mean; blank versus 0; all-zero rule), batch roll-up (simple average over courses with a value), `BatchInput`, `CountStatus` (core and non-core).
- `Precision` per level (question, CO, course, PO, batch): truncate, round half-up or none.
- `IndirectInput` as entered value; direct-only attainment reported next to total.
- `TargetRevise` rule library (manual default, add points, add percent, multiply; keep or lower).
- `AggregateToCO` alternatives (marks-weighted, student-level) for other colleges' methods.
- Two published methods from other colleges written as configs with expected numbers (DS-E).

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | Golden R1 and R2 including PO/PSO values | Exactly as R1 and R2 |
| A2 | Golden R3 batch (DS-B) | Direct and total values and course counts as R3; PO9 Not attained |
| A3 | Same batch with display comparison and rounding | PO9 total compared as 2.86: Attained (configuration switch only) |
| A4 | Precision per level | 2.8594 → 2.85 truncated, 2.86 rounded; 2.845 → 2.85 half-up; "none" keeps all digits |
| A5 | Two sections, same paper, known values | Course = mean of section CO attainments; each section stays visible; other stages give the documented values |
| A6 | CO-PO mapping | Blank stays blank, 0 stays 0; four-CO course averages four values; PO with all zeros is blank by default, 0 by option |
| A7 | Indirect entered | Reports total and direct-only; label "entered" |
| A8 | Targets | Near-target warning within 0.01; revision rules table-driven (met/not met × each rule) |
| A9 | Property tests | Percentages in 0 to 100; level inside bands; adding a passing student never lowers a percentage; student order never changes results; rerun identical |
| A10 | Second and third method (DS-E) | Each expressed by configuration only, with no code change, and equal to the published numbers |
| A11 | Trace completeness | Every output value has a trace entry (inputs, rule, counts, output) |
| A12 | Speed | One course under 100 ms; 100-course batch under 2 s in CI |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Run the batch from the command line on DS-B | Table equals R3; any difference from the mentor's file explained in a note |
| M2 | Read the trace for the PO9 total; switch the comparison setting | Shows 2.8594 against 2.86 and "Not attained"; after switching, shows the rounded value used and "Attained" |
| M3 | A person outside the engine team reads a second-method config | Can explain what it does (readability of the schema) |
| M4 | Mentor reviews rules guide v1 | Accepted, or a correction list is recorded |

**Expected output:** engine version 0.3.0 produces R1 to R4 and matches two other published methods. **Dependency:** the two published methods must be collected before A10 can be written (section 9).

---

### v0.4.0: Academic structure and roster

**Goal:** the app knows the college: departments, programmes, batches, courses, sections, faculty and students, whatever the roll-number scheme.

**What is done**
- University, college, department, programme, batch, academic year, term.
- Course (stable identity) with several codes, course groups (open electives, twin courses), course offerings, sections that carry programme and batch, faculty assignments.
- Student, identifiers (roll number, hall ticket, external id) with validity periods, batch memberships, section memberships, enrolments, statuses (active, withdrawn, detained, graduated).
- Roster import from Excel or CSV with preview, reconciliation and all-or-nothing commit.
- Setup screens through the Django admin; audit on every change.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | Gap roster 1-4, 6-8 (DS-C) | 7 students; none created for 5 |
| A2 | Ranges: A 1-100 and B 1-89; A 1-66 and B 67-130; alphanumeric `1602-23-748-001` | All imported with correct counts per section |
| A3 | Same roll number in two sections | Two different students |
| A4 | Roll number changes | Same student, identifier history kept |
| A5 | Section change | History kept; the enrolment's section decides where marks count |
| A6 | Withdrawn student; "not enrolled" versus "enrolled with no mark" | History kept; the two states are different in queries |
| A7 | Course with two codes; twin courses in one group; open-elective group | One course identity; groups link correctly |
| A8 | Roster import with duplicates, bad rows, missing students | Preview reports each; nothing saved until confirmed |
| A9 | Isolation sweep over new tables and pages (auto-discovered) | Zero leaks |
| A10 | Lecturer assignment scope | Lecturer sees only assigned sections |
| A11 | Audit events | Every create and update logged with actor and time |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Build the demo structure: department → programme → batch → term → course → offering → sections | Hierarchy visible and navigable |
| M2 | Import the anonymised Deep Learning roster (DS-A) | Preview: 67 new, 0 errors; after confirm, 67 listed |
| M3 | Re-import with two students removed and one added | Preview lists exactly those three differences |
| M4 | Upload a roster with a duplicate and a malformed row | Plain messages with row numbers; nothing saved |
| M5 | Move one student to another section; withdraw another | Both histories visible |

**Expected output:** Deep Learning section with 67 students exists, rosters of all DS-C shapes load correctly.

---

### v0.5.0: Outcomes, question papers and methods

**Goal:** everything a course needs before marks exist: outcomes, mapping, targets, exam structure and the method (rules) that will be used.

**What is done**
- Programme outcomes (PO, PSO, PEO), course definition versions, course outcomes, CO-PO/PSO map grid (blank, 0, 1, 2, 3).
- Targets per course per term and per programme PO.
- Assessments, questions, parts (max marks, CO tag or "all COs"), choice groups (best N, best K parts), per-part pass-mark override with reason and IQAC approval, copy a paper from last year.
- Methods and method versions (draft → active, immutable, content hash); assignment with inheritance (university → college → programme → course) and locks; templates for the Vasavi theory and lab methods; validated form editor.
- Import of COs and CO-PO map from Excel.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | CO-PO grid saved and reloaded; values outside blank/0/1/2/3 | Blank stays blank, 0 stays 0; others rejected |
| A2 | Course with four COs | Accepted; CO5 absent everywhere |
| A3 | Paper validation | Totals add up; every part tagged; choice group valid (N not above question count; K not above part count) |
| A4 | Override without reason; override not yet approved | Refused; unapproved override is not used by the engine |
| A5 | Method lifecycle | Activating a draft creates an immutable version with a hash; editing an active version is blocked; an earlier term keeps its version; a later term picks the new one |
| A6 | Inheritance and locks | Most specific wins; a locked university value cannot be changed by a college |
| A7 | Form validation | Errors name the field and the problem |
| A8 | Import the Deep Learning papers | Internal-I 14 parts, Internal-II 12 parts with "best 4 of 6", SEE 25 parts with "best 5 of Q11 to Q17" and "best 2 of Q17"; maxima and CO tags equal the workbook |
| A9 | Targets | Stored per course and term; programme PO targets stored |
| A10 | Isolation sweep over new tables | Zero leaks |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Build the Internal-II paper by hand in the editor | 12 parts, CO tags and "best 4 of 6" match the workbook headers |
| M2 | Enter the Deep Learning CO-PO map | Matches the report; blank and 0 look different |
| M3 | Create a draft from the Vasavi theory template, change pass mark to 55, activate | New version dated; earlier term still shows version 1 |
| M4 | Try to edit the active version | Blocked with an explanation and a "create new draft" option |
| M5 | Add a per-part override with and without a reason | Refused without a reason; with a reason it shows "waiting for IQAC approval" |

**Expected output:** Deep Learning fully set up (three papers, CO-PO map, target 2.2, method version 1 active) with no marks yet.

---

### v0.6.0: Marks entry and import

**Goal:** lecturers and the exam branch can get every mark into the system quickly and safely.

**What is done**
- Mark sheet rows and mark cells with all states (value including 0, blank, absent, withheld, exempted, not applicable, not attempted); attempts (regular as default).
- Change history for every edit; reason required after submission.
- Marks grid (Excel-like: keyboard, paste from Excel, cell checks, auto-save, row version to prevent overwrites).
- Pre-filled Excel template per section and assessment; import with preview, all-or-nothing commit, file kept.
- SEE: script-number mapping and SEE import by script number.
- Quiz, assignment and lab sheet types.
- Section scope enforced for lecturers; exam branch limited to SEE.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | Store and read states | 0, blank, absent, not attempted stay distinct; engine adapter maps them as configured |
| A2 | Validation | Above maximum, negative, non-numeric and unknown state code rejected |
| A3 | Two saves to the same cell | Second is refused with "changed by X, reload" |
| A4 | History | Every edit writes who, when, old, new; after submission a reason is required |
| A5 | Template round trip | Download, fill by script, upload: marks equal |
| A6 | Bad imports: unknown roll, above max, duplicate row, wrong sheet | Row-level report; database unchanged; valid unrelated rows never corrupted |
| A7 | SEE import | Unmapped script reported; two scripts for one student reported; extra answers warned and then reduced by the best-N rule |
| A8 | File safety | Formula cell without cached value rejected with a clear message; workbook with charts handled; XML attack sample rejected; oversize rejected |
| A9 | Permissions | Lecturer A cannot read or write section B; exam branch only SEE; auditor read-only |
| A10 | Import the anonymised Vasavi workbooks | Internal-I 67 × 14; Internal-II 67 × 12 with 281 blanks stored as not attempted; quiz and assignment 67 × 6; lab 67; SEE 66 × 25 |
| A11 | Browser test | Lecturer pastes a block from the clipboard, saves, reloads: values persist |
| A12 | Isolation sweep over new tables | Zero leaks |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Enter marks using only the keyboard (Tab, Enter, arrows; `AB` and `-`) | Fast and predictable; errors shown on the cell; record how long a section takes |
| M2 | Copy a block from the real Excel sheet and paste into the grid | Same values appear |
| M3 | Download the template, fill it in Excel, upload | Preview all green; confirm loads the marks |
| M4 | Upload a file with a wrong roll number and a mark above the maximum | Plain errors with row numbers; nothing saved |
| M5 | Two browsers edit the same cell | Second save refused politely |
| M6 | Open the history of one cell | Shows every change with user and time |
| M7 | Exam branch uploads the script mapping and SEE marks | Unmatched scripts listed before confirm |

**Expected output:** all Deep Learning marks loaded through the app; counts equal the workbook's (67 students, 66 SEE scripts).

---

### v0.7.0: Results and explanations (first end-to-end)

**Goal:** from roster and marks to a trustworthy, explainable course result on screen.

**What is done**
- Input snapshot builder; calculation runs (latest run per scope, permanent on snapshot); result values stored.
- Section, offering and course result pages; CO-PO/PSO table; target and status.
- Explain panel on every number (trace with counts, denominators, attempt rate, exclusions, method and engine version, input hash).
- Provisional versus complete with a checklist of what is missing; flags (below 10%, missing data, small groups, attempt rate).
- Automatic recalculation when marks, mapping, target or method change.
- Indirect value entry by IQAC with the label "entered, not measured"; direct-only shown.
- Round or truncate per level in the interface; band-edge marker; Excel export of the result table.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | End-to-end: load DS-A through the importers, open the course result | Page values equal R1; after approving the Internal-II overrides, equal R2 |
| A2 | Change one mark, one mapping value, the target, the method assignment | The affected runs update; the trace shows the new counts |
| A3 | Remove one student's whole mark sheet | Run is provisional with a checklist item; blank choice parts do not cause this |
| A4 | Below-10% case and a `MissingData` case | Flagged and provisional until released |
| A5 | Two sections, same paper; shared offering for two programmes | Course = mean of section results; each programme's result uses only its own sections |
| A6 | Explain for SEE CO2 | Lists every part with pass count, denominator, attempt rate, exclusions, method and engine version, input hash |
| A7 | Same inputs twice | Same input hash and same outputs |
| A8 | Withdrawn student; section change | Included or excluded per the configured rule |
| A9 | Denominator below 10 | Small-group warning shown |
| A10 | Speed with 130 students × 30 parts | Course page under 1 s |
| A11 | Permissions | Lecturer sees only own sections; HOD sees the department |
| A12 | Isolation sweep over new pages | Zero leaks |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Coordinator opens the Deep Learning result and compares with R1; reads three explain panels | Every cell matches; someone outside the team can follow the explanations |
| M2 | Change a quiz mark so a pass count changes | Result and count update |
| M3 | Delete one student's sheet | Provisional banner and "what is missing" list |
| M4 | Enter indirect value 3 | Labelled "entered, not measured"; direct-only attainment visible |
| M5 | Switch the course level to round | Display changes; compared value stays unrounded; near-target warning when within 0.01 |
| M6 | Export the result table to Excel | Opens; equals the page |

**Expected output:** the Deep Learning course result on screen equals R1 (default) or R2 (with approved overrides), every number explainable.

---

### v0.8.0: Workflow and governance

**Goal:** results follow the college's approval process and cannot change silently after signing.

**What is done**
- Section and assessment states: draft → submitted → accepted or returned (with reason).
- Course result states: reviewed → approved → signed; marks lock at approval; reopen with a reason creates a new run and a new signature cycle.
- Overrides: allowed roles, mandatory reason, optional approval, original kept, downstream steps use the override, allowed only before approval; release of results stopped for review.
- Signed run frozen (snapshot and hash); "differs from signed" banner after later changes.
- Inbox of tasks per role; college audit viewer; the role table of design section 9 enforced; platform admin sees no marks by default; time-limited support grant.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | State machine, table-driven | Every legal move allowed for the right role; every illegal move refused |
| A2 | Locks | After approval, edits refused in the service layer and by a database check; reopen with reason unlocks and starts a new run |
| A3 | Override | Needs role and reason; original kept; downstream values use it; trace shows both; refused after approval |
| A4 | Freeze | Signed run unchanged after a reopen and edit; direct database change of a signed run fails; banner appears |
| A5 | Signature record | Name, role, time and content hash stored |
| A6 | Role matrix | Generated from design section 9: every role × action gives the expected allow or deny |
| A7 | Audit | Every transition, override and reopen logged with before, after and reason |
| A8 | Support grant | Expires at the set time |
| A9 | Isolation sweep over new pages | Zero leaks |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Walk through with four people: lecturer submits; coordinator returns with a reason; lecturer fixes; coordinator accepts and reviews; HOD approves; principal signs | Each step visible to the right person only; Deep Learning result frozen |
| M2 | After signing, a lecturer tries to edit; HOD reopens with a reason; edit; recalculate | Edit refused first; after reopen both versions viewable |
| M3 | HOD overrides a SEE level with a reason; a lecturer tries the same | Marker "2 → 3 overridden" on the page; lecturer has no option |
| M4 | Check each role's inbox | Only relevant pending items |
| M5 | Open the audit viewer | The walkthrough appears in order |

**Expected output:** a signed Deep Learning result that no ordinary action can alter, with a complete trail.

---

### v0.9.0: Department, batch and quality loop

**Goal:** results above the course (programme and batch) and the college's quality process.

**What is done**
- Batch roll-up from signed course runs (default), per programme and batch; indirect PO entry; PO/PSO targets; status; attained and not-attained counts split into core and non-core.
- Historic results (earlier batches) imported; three-batch comparison.
- Import of an old workbook's values and a side-by-side comparison with computed values.
- Target revision proposal (manual by default).
- Gap view: COs and POs below target; weakest questions.
- Observations, action plans, actions taken with dates and proof files (size and type limits).
- Batch sign-off flow (prepared → HOD → principal) and freeze, recording the course runs used.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | Load DS-B course values and open the CSE 2021-25 batch page | Direct and total values equal R3; PO9 Not attained |
| A2 | Signed versus latest | Default uses signed course runs only and lists excluded unsigned ones; the other setting includes them with a marker |
| A3 | Shared definition, separate programmes | CSE and CSE-AIML batch results are separate |
| A4 | Core and non-core counts | 50/51, 29/29, 48/51, 28/29, or every difference listed by course |
| A5 | Three-batch comparison | 2019-23 and 2020-24 values equal the file's chart table |
| A6 | Compare view | Computed against old workbook values: differences highlighted at the configured precision |
| A7 | Gap view | Lists COs below target and the lowest-percentage questions in order; Deep Learning shows CO5 at Level 1 under R1 |
| A8 | Quality loop | Last year's plan appears on the new offering; action taken with date and proof; file limits enforced |
| A9 | Batch freeze | Signed batch report does not change when a course run changes later |
| A10 | Detained or backlog student | Counted in the batch of the section where enrolled |
| A11 | Speed | Batch of 100 courses × 15 POs renders under 3 s |
| A12 | Isolation sweep over new pages | Zero leaks |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | IQAC opens the CSE 2021-25 batch page and compares to the mentor's file | Same numbers; each difference has a written note |
| M2 | Change the PO9 comparison setting | Status flips; the report says which value was compared |
| M3 | Upload an old workbook | Side-by-side view with differences marked |
| M4 | Lecturer writes observations and an action plan; next year's offering shows it; add an action taken with a PDF | Linked and dated |
| M5 | HOD finds the weakest CO using the gap view | Found without help |

**Expected output:** R3 on screen, a signed and frozen batch report, and a working action-plan trail.

---

### v0.10.0: Reports and exports

**Goal:** the printable and exportable outputs the college uses today (project statement section 12).

**What is done**
- PDF reports from HTML templates: per-assessment CO sheets; theory course analysis (with observations, action plan, signature blocks); lab analysis; CO-PO/PSO table; Action Taken Report; department and batch report with three-batch chart; explanation appendix.
- NBA flat course list (Excel); Excel export of every table; full college export (Excel and JSON).
- Footer on every report: college, programme, batch, course, term, method version, engine version, run id, data status, generated time, content hash. Provisional reports watermarked.
- Per-college template override; layouts follow the mentor's documents.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | Render every report for DS-A and DS-B | No errors; valid PDFs with pages |
| A2 | Footer and watermark | All footer fields present; watermark only when provisional |
| A3 | Numbers in PDF text against result pages | Equal for R1, R2 and R3 |
| A4 | Content hash | Printed hash equals the stored hash of the frozen run |
| A5 | Excel exports | Reopen and compare values with the pages |
| A6 | NBA list | One row per course; columns as defined |
| A7 | Largest report (batch, eight semesters) in a 512 MB container | Renders within the memory and time limits |
| A8 | Regenerate a signed report | Identical content |
| A9 | One college's template override | Does not affect another college |
| A10 | Full export | Contains every entity with matching counts |
| A11 | Report access | Follows the role table |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Print each report and compare with the mentor's documents using a section-by-section checklist | Differences listed; mentor feedback recorded |
| M2 | Open a provisional report, complete the data, open again | Watermark disappears |
| M3 | Print on A4 and check signature blocks | Room for signatures; nothing cut off |
| M4 | Open the PDFs in two browsers or viewers | Same appearance |
| M5 | Export the batch to Excel and open in Excel and LibreOffice | Opens; values correct |

**Expected output:** a set of PDFs and Excel files for Deep Learning and CSE 2021-25 that match the app's numbers and the college's formats.

---

### v0.11.0: Hardening, privacy and operations

**Goal:** safe to run with real data: secure, recoverable, documented.

**What is done**
- Security review (checklist based on common web risks); upload abuse protection; rate limits; dependency and secret scanning in CI.
- Backups (database and files, encrypted), restore script, scheduled restore test, healthchecks; `update.sh` with backup, migrate and health check; production compose file with HTTPS (public or internal certificate).
- Audit hash-chain verify command.
- Privacy tools: per-student export, retention list with advance notice and anonymisation that keeps the audit chain valid; anonymise script for fixtures and demo data; log retention rules.
- Performance suite on synthetic data (10 colleges × 8 programmes × 4 years).
- Demo deployed on free hosting with anonymised data.
- Documents: user guide, rules guide, admin guide, known limits.

**Automatic tests**
| ID | Test | Expected |
|---|---|---|
| A1 | Dependency audit, static security scan, secret scan | No critical findings |
| A2 | Rate limits and lockout | Enforced |
| A3 | Upload abuse: oversized file, wrong type, decompression bomb, XML entity attack | All rejected safely |
| A4 | Backup → restore into a scratch database; recalculate R1, R2, R3 | Row counts equal; results equal; wrong key fails |
| A5 | Full isolation sweep: every discovered endpoint × two colleges | Zero leaks |
| A6 | Audit chain verify; tamper with one row | Passes normally; tamper detected |
| A7 | Performance suite | Batch run under 5 s; grid 130 × 30 under 2 s; results page under 1 s |
| A8 | Retention tool | Lists students past retention, waits the notice period, anonymises; audit chain still valid |
| A9 | Update from the previous tag on a seeded database | Migrations pass; health check passes; rollback restores |
| A10 | Container checks | Runs as non-root; no secrets in image layers |
| A11 | Accessibility scan on key pages | No critical violations |

**Manual tests**
| ID | Steps | Expected |
|---|---|---|
| M1 | Install on a clean Linux server following the admin guide | Working HTTPS site; backup job scheduled |
| M2 | Delete the database; restore from the last backup with the key | Last signed report unchanged |
| M3 | Stop the app container in the middle of an import | No partial data after restart |
| M4 | Review the privacy notice template and one student's data export | Complete and understandable |
| M5 | A new lecturer follows the user guide to enter marks, watched by an observer | Completes unaided; blockers noted |
| M6 | Open the demo after it has been idle | First page loads after the documented wake-up; later pages are fast |

**Expected output:** documentation set, deployed demo, a proven restore, and a clean security and isolation report.

---

## 6. v1.0.0: the prototype release

**Goal:** the prototype with most of the major features, ready to show the mentor and to start a parallel run at a college.

### 6.1 What v1.0.0 contains
| Area | In v1.0.0 |
|---|---|
| Academic structure, rosters, any roll-number scheme, history | Yes (v0.4.0) |
| Outcomes, CO-PO map, targets, question papers with choice rules | Yes (v0.5.0) |
| Configurable, versioned methods (config as data) | Yes (v0.2.0, v0.3.0, v0.5.0) |
| Marks entry, Excel import, SEE script mapping, mark states, history | Yes (v0.6.0) |
| Automatic calculation with explanations; provisional results | Yes (v0.7.0) |
| Approvals, signing, freezing, overrides with reasons, reopen | Yes (v0.8.0) |
| Department and batch results, comparison, gap view, action plans | Yes (v0.9.0) |
| PDF and Excel reports, NBA list | Yes (v0.10.0) |
| Roles, college separation (app and database), audit, backups, privacy tools | Yes (v0.11.0) |
| Round or truncate per level, strict or approved pass marks | Yes |

### 6.2 What v1.0.0 does not contain (moves to later versions)
Method wizard and dry-run diff, two-factor login, email reminders, Google sign-in (v1.1.0); indirect surveys (v1.3.0); REST API (v1.4.0); single sign-on, translations, mobile marks entry (v1.5.0); credit-weighted roll-up screens and ERP adapters (v2.0.0).

### 6.3 Release work (no new features)
- Stabilise: fix defects found by the acceptance run; remove known blockers.
- Final demo data (anonymised Vasavi data, plus a second synthetic college with a different roll scheme).
- Complete user, rules and admin guides; known-limits list; open-items list (section 9).

### 6.4 Automatic tests
| ID | Test | Expected |
|---|---|---|
| A1 | Acceptance suite: one named test for each of the 20 scenarios (section 8.2) | All 20 pass |
| A2 | Every earlier test on the release-candidate image | All pass |
| A3 | Golden R1, R2, R3, R4 | Unchanged since v0.3.0 (or changes documented) |
| A4 | Upgrade from the last v0.11.x demo database | Migrations pass |
| A5 | Backup and restore drill script | Passes |
| A6 | Isolation sweep | Zero leaks |
| A7 | Second method (DS-E) | Still passes by configuration only |

### 6.5 Manual tests
| ID | Steps | Expected |
|---|---|---|
| M1 | Demo script for the mentor: (1) log in as IQAC; (2) show method version; (3) show the Deep Learning paper and CO-PO map; (4) lecturer pastes marks; (5) open the course result; (6) open three explanations; (7) compare R1 with the college's report and show the Internal-II pass-mark difference; (8) approve the override; (9) see R2; (10) coordinator, HOD and principal sign; (11) try to edit after signing; (12) open the batch page; (13) change the PO9 comparison; (14) print the course report; (15) show the audit trail | Every step works without developer help; mentor notes recorded |
| M2 | A lecturer who has not seen the app enters a section's marks from the user guide | Unaided; blockers noted |
| M3 | Create a second college with a different roll scheme (A 1-100, B 1-89) and a different method using only screens and imports | Works with no code change |
| M4 | Walk through the open-items list with the mentor | Each item has an owner and a version |
| M5 | Mentor sign-off of the rules guide | Signed or corrections listed |

**Expected output:** tag **v1.0.0**, a demo address, the user, rules and admin guides, a full test report, and the open-items list. The reference numbers on screen are R1 (default) and R2 (with approved overrides), R3 for the batch.

---

## 7. After v1.0.0

### v1.0.x (patches)
Bug fixes from the demo and the parallel run. Each patch: a failing test first, the fix, no rule, schema or feature change. Expected: all earlier tests plus the new regression test pass.

### v1.1.0: Pilot readiness
- **Scope:** guided method wizard (plain-language questions); dry-run diff (run a new method on last term's data and show what changes); two-factor login for admin, IQAC and HOD; nightly audit-chain verification job; email reminders for marks due and approvals waiting; optional Google sign-in; improvements to the parallel-run compare view; usability fixes from observation.
- **Automatic:** wizard output validates and equals the hand-built config for the Vasavi method; dry run on DS-A with pass mark changed from 60 to 55 shows the exact list of changed values and status flips; two-factor enrolment and login; tampered audit row raises an alert; reminder jobs queue the right messages; sign-in with a test Google account.
- **Manual:** a coordinator builds a method with the wizard without help; dry run shown to the mentor; reminder email received; two-factor with a phone app.
- **Expected output:** a college can set itself up with less developer help, and every method change is previewed before it is activated.

### v1.2.0: Methods and rules from the pilot
- **Scope:** apply decisions still open after the pilot (target revision rule, lab details, supplementary exam policy, the college's decision on strict versus approved pass marks); add further methods as configurations; add a new step type only where a real method cannot be expressed; more report layouts per college.
- **Automatic:** golden tests for each new method; target revision table-driven by the chosen rule; regression of R1 to R4; schema converter test for any method-schema change.
- **Manual:** the college's IQAC reviews three real course results against their own Excel; parallel-run difference list is empty or fully explained.
- **Expected output:** the parallel run reaches "zero unexplained differences".

### v1.3.0: Indirect attainment
- **Scope:** survey forms and scales, mapping to COs and POs, response-rate rule, student surveys for indirect CO, recruiter, stakeholder and alumni surveys for indirect PO, weights; replaces the typed indirect value; anonymity and privacy for responses.
- **Automatic:** survey scoring cases from the mentor's indirect workbooks (when received); response-rate rule; indirect value flows into CO and PO totals; entered-value mode still works.
- **Manual:** run one survey with a small group; check results against a hand calculation.
- **Expected output:** totals use measured indirect values; reports no longer say "entered, not measured".

### v1.4.0: Integration (read side)
- **Scope:** read-only REST API with OpenAPI description and per-college API keys; webhook when a result is signed; documented import and export formats; adapter layer for the first target ERP file format.
- **Automatic:** API contract tests; key scoping (one college's key cannot read another's data); rate limits; webhook delivery and retry.
- **Manual:** a script (or a sample ERP export) reads signed results using only the documentation.
- **Expected output:** external systems can read results without database access.

### v1.5.0: Access and reach
- **Scope:** single sign-on (OpenID Connect or SAML); translations; mobile-friendly marks entry; accessibility fixes.
- **Automatic:** SSO login with a test provider; translation files complete for the chosen language; accessibility scan clean on key pages; mobile viewport browser test for entry.
- **Manual:** log in with a college account; enter a few marks on a phone; read one page in the second language.
- **Expected output:** staff use their existing college accounts; entry works on a phone.

### v2.0.0: Multi-college operations
- **Scope:** college onboarding automation; credit-weighted roll-up screens; write side of the API (rosters, marks) and standard formats (OneRoster, LTI launch); decision and implementation for a hosted multi-college service if wanted; any breaking changes accumulated (with migration guide).
- **Automatic:** migration from the last v1.x on a large seeded database; write API validation and audit; isolation sweep with many colleges; load test at the planned number of colleges.
- **Manual:** onboard a new college from zero using only the guide; push a roster from a sample ERP; compare credit-weighted and equal-weight batch results.
- **Expected output:** a new college is live without developer time; existing signed results unchanged.

---

## 8. Traceability

### 8.1 Functional requirements by version
| Requirement | First complete in |
|---|---|
| F1 structure, users, roles | v0.1.0 (roles), v0.4.0 (structure) |
| F2 course identity, F3 electives and twins | v0.4.0 |
| F4 outcomes and mapping, F5 assessments | v0.5.0 |
| F6 entry and import, F7 mark states, F8 validation and source, F9 history | v0.6.0 |
| F10 lock and reopen, F19 approvals and freeze, F20 overrides | v0.8.0 |
| F11 automatic calculation, F12 intermediate values, F13 recalculation and versions, F14 provisional and flags | v0.7.0 (engine in v0.2.0 and v0.3.0) |
| F15 section, course, department, batch | v0.7.0 and v0.9.0 |
| F16 targets and revision | v0.5.0 (set), v0.7.0 (status), v0.9.0 (proposal) |
| F17 observations and action plans, F18 gap view | v0.9.0 |
| F21 reports | v0.10.0 |
| F22 import old Excel, side by side | v0.9.0 |
| F23 scoped access, separation, audit | v0.1.0 (base), v0.11.0 (full sweep) |

### 8.2 Acceptance scenarios by version
| # | Scenario | Engine / data first passes | Fully passes on screen |
|---|---|---|---|
| 1 | Reference course | v0.2.0 | v0.7.0 |
| 2 | Reference batch | v0.3.0 | v0.9.0 |
| 3 | Gaps, ranges, alphanumeric ids | v0.4.0 | v0.4.0 |
| 4 | Same roll number in two sections | v0.4.0 | v0.4.0 |
| 5 | Withdrawal and section change | v0.4.0 | v0.7.0 |
| 6 | Blank versus zero versus absent | v0.2.0 | v0.6.0 |
| 7 | Boundary at exactly 60% | v0.2.0 | v0.7.0 |
| 8 | Best 5 of 7 with parts | v0.2.0 | v0.6.0 |
| 9 | Shared CO across internals | v0.2.0 | v0.7.0 |
| 10 | Quiz and assignment apply to every CO | v0.2.0 | v0.7.0 |
| 11 | Below 10% flagged | v0.2.0 | v0.7.0 |
| 12 | Section roll-up | v0.3.0 | v0.7.0 |
| 13 | Override with role and reason | v0.8.0 | v0.8.0 |
| 14 | Configuration change applies to later periods | v0.5.0 | v0.7.0 |
| 15 | Incomplete data is provisional | v0.7.0 | v0.7.0 |
| 16 | Second method on paper | v0.3.0 | v1.0.0 (M3) |
| 17 | Saved configuration reused | v0.5.0 | v0.5.0 |
| 18 | Bad import | v0.6.0 | v0.6.0 |
| 19 | Data isolation | v0.1.0 (checked in every version) | v0.11.0 |
| 20 | Signed report frozen | v0.8.0 | v0.10.0 (PDF) |

---

## 9. Open items and when each is needed

| Item | Who | Needed by | What happens until then |
|---|---|---|---|
| Two published methods from other colleges (DS-E) | Team | Before v0.3.0 test A10 | Test is written when the methods are collected; if missing, it moves to v1.2.0 |
| Confirm Internal-II is "answer any 4 of 6" from the question paper | Mentor | Before v0.5.0 manual test M1 | Configured as best 4 of 6; levels do not change either way on the reference data |
| College decision: strict 60% (2.18) or approved typed pass marks (2.32) | College IQAC and mentor | Before the parallel run (after v1.0.0) | App defaults to strict 60%; overrides available |
| Target revision rule (+0.5 points, +0.5%, ×1.1) | Mentor | v1.2.0 | Targets set by hand |
| Under-18 students and parental consent for academic records | College legal or IQAC | Before real data | Demo uses anonymised data only |
| Free-tier terms for the demo (Render, Neon) | Team | Before the v0.11.0 deployment | Re-check on the vendors' own pages |
| Indirect survey design and workbooks | Mentor | v1.3.0 | Indirect value is entered by IQAC |
| Report layouts from the mentor's documents | Mentor and team | v0.10.0 | Templates built from the sample reports already received |
