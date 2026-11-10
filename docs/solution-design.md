# Solution design: configurable OBE attainment platform

**Version 1.2** · 2026-11-09 · Status: **design with your decisions applied; reviewed strictly twice**
**Changes:** v1.1 (2026-11-08) and v1.2 (2026-11-09) are logged in section 22. v1.2 applies your 12 decisions (section 21) and fixes 43 issues from a strict review.
**Inputs:** `project-statement-final.md` v2.0 (requirements), `solution-options.md` (options compared), mentor's course and batch workbooks.
**Evidence:** a working prototype of the calculation engine in `prototype/` (section 2).

Contents
1. Summary and assumptions
2. Validation done before writing this design (read first)
3. Architecture
4. Tech stack
5. Data model
6. Calculation engine
7. Configuration management
8. Workflows
9. Roles and permissions
10. Screens and usability
11. Import, export and reports
12. Audit trail, versions, locking
13. Security, privacy, multi-college isolation
14. Hosting, deployment, backups, operations
15. Integration readiness (later ERP)
16. Testing and acceptance
17. Code structure and conventions
18. Delivery plan
19. Requirements traceability (checked item by item)
20. Critical review of this design
21. Decisions (made 2026-11-09) and what is still open
22. Review log (v1.1 and v1.2)

---

## 1. Summary and assumptions

### 1.1 The design in one screen
- **Architecture:** one web application (modular monolith) with a **pure calculation engine** inside it, one PostgreSQL database, server-rendered pages with small interactive parts.
- **Engine:** each college's method is **saved as data**: a versioned list of ready-made calculation steps with settings. No college writes code. Every result carries a full explanation and the config version used.
- **Stack:** Python 3.12, Django 5.2 LTS, PostgreSQL 16+, HTMX, Jspreadsheet CE (or Tabulator) for marks entry, openpyxl for Excel, WeasyPrint for PDF, Chart.js for charts, Docker for packaging.
- **Separate colleges:** every row carries `college_id`; enforced twice (in the app and by PostgreSQL row-level security).
- **Hosting (all free):** demo on Render free + Neon free PostgreSQL (anonymised data; nightly encrypted backup by GitHub Actions); real college use on the college's own server with Docker (nightly encrypted backup by a local job plus an off-site copy).
- **Proof it works:** the prototype engine reproduces the mentor's Deep Learning results exactly (all levels, CO values, course 2.32, all 8 PO/PSO values) when the college's typed Internal-II pass marks are entered as overrides, and the CSE 2021-25 batch roll-up exactly (all 15 PO/PSO direct values). It also showed that ordinary floating-point maths would print the reference CO1 as 2.51 instead of 2.52.
- **Your decided defaults change one official result:** with a strict 60% pass mark (decision 1), Deep Learning is **2.18, Not attained**, not the 2.32 Attained in the college's report. The college must know this before the pilot (section 20.2).

### 1.2 Assumptions (A1 to A3 and A7 confirmed by your decisions on 2026-11-09; the rest are still assumptions)
| # | Assumption | If wrong, what changes |
|---|---|---|
| A1 | Team of 3 to 5 students who know Python basics and HTML | Java team: swap Django for Spring Boot; the design (sections 3, 5 to 13) stays the same |
| A2 | About 5 to 6 months to a pilot | Shorter: cut release 1 to the "must" list in section 18 |
| A3 | First a demo for the mentor, then one pilot college (Vasavi), then others | Many colleges at once: add onboarding automation earlier |
| A4 | Nobody will register a credit card | Oracle VM, Google Cloud options drop out (Render + Neon still work) |
| A5 | Laptops/desktops for marks entry; phones only for viewing | Phone entry: add a mobile marks form (simple list) |
| A6 | Internet is available during entry | Offline need: add "download template, fill offline, upload" (already in design) as the main path |
| A7 | Free/open-source project under the **MIT licence** (decided) | Selling later is allowed by MIT; all chosen libraries are MIT/BSD/Apache/MPL-compatible |
| A8 | Staff sign in with email + password; Google sign-in optional | College SSO needed: add an identity provider later (section 15) |

---

## 2. Validation done before writing this design (read first)

I built the core of the proposed engine (`prototype/engine.py`) and ran the mentor's real workbooks through it. Results in `prototype/course-results.txt` and `prototype/batch-results.txt`.

### 2.1 What was proved
| Check | Result |
|---|---|
| Course: question pass → % per question → CO average → level | Every per-question pass count matches the workbook's own counts (14 Internal-I, 12 Internal-II, 25 SEE parts) when the sheet's own pass marks are used |
| Course: levels, direct CO, final CO, course attainment, PO/PSO | **Exact match** with Appendix A: levels 3/3/3/3/3 internal, 2/2/2/1/1 SEE; CO 2.52, 2.52, 2.52, 2.04, 2.04; course 2.328 → **2.32 Attained**; PO1 2.29, PO2 2.28, PO3 2.41, PO4 2.38, PO5 2.31, PSO1 2.28, PSO2 2.32, PSO3 2.32 |
| Best 5 of Q11 to Q17 | Works. Script 11 had 6 questions entered; the step drops the weakest (Q17), levels unchanged |
| Truncation | Exact decimals truncate 2.328 → 2.32 and 2.2985 → 2.29 correctly (floats would risk wrong digits) |
| Batch: direct PO = simple average of course values | **Exact match** for all 15 PO/PSO (84 courses for PO1 down to 6 for PO11); total = 0.8 × direct + 0.2 × 3 matches |
| Roster | Same 67 roll numbers in 4 sheets; 66 in the SEE (by script number) |
| Edge cases (synthetic data, `prototype/synthetic-results.txt`) | Best 2 of 3 parts, best 5 with a tie, a student with only 4 answers, a mark exactly at 60% (`>=` passes, `>` fails), merged level 2.5, below 10%, nobody attempting a part: all behave as designed; the last case needed a new rule (6.3 `MissingData`) |
| Exact decimals are required | Searching all level combinations: for internal 3, SEE 2, quiz 3, assignment 3 (the reference CO1), float maths gives 2.5199999999999996, truncated to **2.51**; exact decimals give **2.52** like the report |

### 2.2 What it exposed, and how your decisions settle it
1. **The reference result depends on a typed pass mark.** In Internal-II, the "60% of marks" for the 3.5-mark parts is typed as **2** (57%), not 2.1 (60%).
   - With the typed values: course **2.32, Attained** (matches the report).
   - With a strict 60% rule: Internal-II CO3 drops to Level 2 and CO5 to Level 1; course **2.18, Not attained** (target 2.2).
   - **Decided (2026-11-09):** strict 60% of max by default, with an optional **per-part pass mark** that needs a reason, is approved by IQAC and is printed on reports. Result for Deep Learning with the default: **2.18, Not attained**. With the typed marks entered as overrides: 2.32, Attained (prototype runs G and H).
2. **SEE denominators in the workbook are mixed:** divided by 66 (all SEE students) for Q1 to Q11b, by "attempted" for later parts. Using 66 everywhere would give SEE CO2 and CO3 Level 1 and a course of 2.13.
   - **Decided (2026-11-09):** the denominator is set per question. A **choice** question counts only the students who attempted it; a **compulsory** question counts everyone who sat the assessment.
   - **Result:** this rule is almost exactly what the workbook did. SEE CO1, CO2, CO4 and CO5 percentages match the workbook to 2 decimals (58.80, 51.06, 46.52, 45.57); CO3 is 57.19 instead of 57.43 only because the app applies "best 5" to the one student who wrote 6 answers, and the workbook did not. All SEE levels match the report.
   - **New finding:** Internal-II is **"answer any 4 of 6"** (66 students answered exactly 4; one answered 5). The workbook did not apply a best-4 rule; the app will (configured), and levels do not change (prototype runs I and J).
3. **Rounding differs by level.** The course level truncates (2.328 → 2.32), but the batch chart table **rounds** (PO1 2.7999 → 2.80; PO12 2.6998 → 2.70). Truncating everywhere would print 2.79 and 2.69.
   - **Status flip found: PO9 (CSE 2021-25)** total is 2.8594 against a target of 2.86. It is **Not attained** if compared unrounded or truncated, and **Attained** only if rounded first.
   - **Conflict in our own rules:** "truncate everywhere" [C] and "prefer the option that gives higher values" [C] disagree here: for PO9, rounding gives the higher (Attained) result.
   - **Decided (2026-11-09):** each level (course, batch) has a setting to **round or truncate**, with the number of decimals. The value compared with the target is a separate setting; default **unrounded**, with a "near target" warning within 0.01. So PO9 stays Not attained unless a college chooses "compare the displayed value" with rounding.
4. **Marks and CO tags are per part in practice.** The SEE sheet stores 11a, 11b … 17c, each tagged to a CO, and percentages are per part. This settles open item 1: **store marks per part; apply the choice rule per question; compute percentages per part.** Q17's "best 2 of 3 parts" never happened in this data (nobody wrote all 3), so it is tested only by synthetic tests.
5. **Minor:** Internal-I uses `>` but no mark sits exactly on 0.6 or 1.8, so `>` vs `>=` changes nothing here. The quiz/assignment sheet has no absent marks, so "absent = 0" is also untested by real data.

---

## 3. Architecture

### 3.1 Style
- **Modular monolith:** one deployable web app, one database, strict internal modules.
- **Why not microservices:** data is tiny (one section ≈ 67 students; a college ≈ a few MB a year), free hosts give one small service, a student team cannot afford the operational overhead, and audit/transactions are simpler in one database.
- **Why not serverless or BaaS:** CPU-time limits (Excel import, PDF), vendor lock-in, and business logic scattered across places (harder to test and audit).
- **Server-rendered pages + HTMX**, with one JavaScript grid only where needed (marks entry). One codebase, one language for most work, session-based login (simplest secure option).

### 3.2 Context
```
 Lecturers, HOD, IQAC, Exam branch, Admin, Auditor
                     │  browser (HTTPS)
                     ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                Attainment web app (Django)                   │
 │                                                              │
 │  Web layer: pages (HTMX), marks grid (Jspreadsheet), JSON API│
 │  ───────────────────────────────────────────────────────────  │
 │  Modules:                                                    │
 │   tenancy · accounts · academics · roster · outcomes ·       │
 │   assessments · marks · methodology · results · quality ·    │
 │   reports · imports · audit · integration                    │
 │  ───────────────────────────────────────────────────────────  │
 │  engine  (pure Python library: no database, no web)          │
 └───────────────┬──────────────────────────────┬───────────────┘
                 │                              │
          PostgreSQL (one DB,            File storage (uploads,
          row-level security)            signed PDFs: database on demo,
                 │                       disk when self-hosted)
                 ▼
      Nightly encrypted backup (demo: GitHub Actions; self-hosted: local job + off-site copy)

 Later: ERP / SIS ──(CSV/Excel now, REST API later)──► integration module
```

### 3.3 Modules and their boundaries
| Module | Owns | Talks to |
|---|---|---|
| `tenancy` | College (tenant), university/affiliation, tenant settings, current-tenant middleware | everyone (provides `college_id`) |
| `accounts` | Users, role assignments with scope, login, password reset | tenancy |
| `academics` | Departments, programmes, batches, academic years, terms, courses, course offerings, sections, faculty assignments | tenancy |
| `roster` | Students, roll-number history, section membership, enrolments, script-number mapping | academics |
| `outcomes` | CO, PO, PSO, PEO definitions (versioned), CO-PO/PSO mapping matrix | academics |
| `assessments` | Assessment instances, question paper structure (questions, parts, max, CO tags, choice groups) | academics, outcomes |
| `marks` | Mark cells with states, entry sessions, change history, locks | roster, assessments |
| `methodology` | Saved methods (config as data), versions, effective periods, templates | tenancy |
| `engine` | Pure calculation: input snapshot → results + explanation trace | nothing (pure) |
| `results` | Runs the engine, stores result snapshots, overrides, targets, statuses, sign-offs | marks, methodology, outcomes |
| `quality` | Observations, action plans, action-taken entries, proof files, gap view | results |
| `reports` | Report definitions, HTML/PDF/Excel rendering, NBA flat list | results, quality |
| `imports` | Upload → parse → validate → preview → commit; import batches | roster, marks, academics |
| `audit` | Append-only audit log, history viewer | everyone writes here |
| `integration` | External ids, export formats, later REST API keys and webhooks | everyone (read) |

Rules for boundaries:
- A module only calls another through its `services.py` (no reaching into another module's tables).
- `engine` imports nothing from Django. It gets plain data classes and returns plain data classes.

### 3.4 Request flow example: "calculate course result"
1. Coordinator opens the course offering and presses **Calculate** (or it runs automatically after marks are saved).
2. `results` collects an **input snapshot**: roster, enrolments, mark cells with states, question paper, CO-PO map, target, and the **methodology version effective for that term**.
3. `engine.run(snapshot, method)` returns: values at every step, counts, denominators, exclusions, flags, and a trace.
4. `results` stores the run (input hash, method version, engine version, outputs) and marks it **provisional** or **complete** (section 6.7).
5. The page shows the result with "Explain" links on every number.

---

## 4. Tech stack

All free and open source. Pin exact versions at project start; upgrade only deliberately.

| Layer | Choice | Why | Free-tier / licence notes |
|---|---|---|---|
| Language | **Python 3.12** | Easiest for students; exact `Decimal`; best Excel libraries | PSF licence |
| Web framework | **Django 5.2 LTS** | Admin screens for setup data (F1 to F5) almost free; auth, sessions, CSRF, ORM, migrations built in; security updates until April 2028 | BSD |
| Database | **PostgreSQL 16 or newer** | Relational data; exact `numeric`; JSONB for method configs; row-level security for isolation | PostgreSQL licence |
| Interactivity | **HTMX 2.x** (+ django-htmx) | Partial page updates without a JS framework | BSD |
| Marks grid | **Jspreadsheet CE** (fallback: **Tabulator**) | Excel-like keyboard, paste from Excel, cell validation | MIT. Not AG Grid Community: its clipboard paste is an Enterprise (paid) feature. Confirm paste and licence in a week-1 spike |
| CSS | **Pico.css** or **Bootstrap 5** | Clean defaults, little custom CSS | MIT |
| Charts | **Chart.js 4** | Simple bar/line charts for CO/PO and batch comparison | MIT |
| Config validation | **Pydantic 2** | Validates method configs (types, ranges, references) with clear errors | MIT |
| Excel | **openpyxl** | Read/write .xlsx, fill college templates | MIT |
| CSV | Python `csv` | Built in | — |
| PDF | **WeasyPrint** | HTML + print CSS → PDF; same template as on-screen report | BSD |
| Row history | **django-simple-history** | Automatic history of setup records | BSD |
| Background work | **None in release 1** (synchronous). If needed later: **django-q2** with the database as broker (no Redis) | Calculations take milliseconds at our size | MIT |
| Web server | **Gunicorn** behind **Caddy** (self-host) | Caddy gets free HTTPS certificates automatically | MIT / Apache |
| Packaging | **Docker + docker compose** | Same setup on laptop, demo and college server | Apache |
| Tests | **pytest, pytest-django, Hypothesis, Playwright** | Unit, property and browser tests | MIT / MPL |
| Code quality | **ruff** (lint + format), **mypy** (engine only) | Fast, one tool | MIT |
| CI/CD | **GitHub Actions** (free minutes for public repos; 2,000 min/month private) | Tests, build image, nightly backup | Free tier |
| Error tracking | **Sentry free Developer plan** or self-hosted **GlitchTip** | Errors with stack traces | Free tier limits apply |
| Uptime | **UptimeRobot free** or **healthchecks.io free** | Alerts when the site is down / backup did not run | Free tier |

Rejected for release 1 (see `solution-options.md`): React SPA (two codebases), Next.js (framework churn, Vercel Hobby is non-commercial), Supabase BaaS (pauses when idle, logic scattered), Spring Boot (heavier memory on free hosts, steeper learning), MongoDB (relational data), rules engines (poor at aggregation), free-text formula languages (out of scope 5.2, error-prone).

---

## 5. Data model

Every tenant-owned table has `college_id` (not null, indexed) and audit columns (`created_at`, `created_by`, `updated_at`, `updated_by`). Primary keys are UUIDs (safe to expose in URLs and exports, no guessing).

### 5.1 Organisation and academics
| Entity | Key fields | Notes |
|---|---|---|
| `University` | name, short_name | Optional parent; holds university-level method (weights same for all departments) |
| `College` (tenant) | name, code, university_id, settings JSON, status | |
| `Department` | college, name, code | |
| `Programme` | department, name (B.E. CSE), level | PO/PSO and PO targets live here |
| `Batch` | programme, name ("2021-25"), start_year, end_year | Graduating cohort |
| `AcademicYear`, `Term` | "2025-26", semester number, dates | |
| `Course` | college, title, internal stable id, category (core/non-core), type (theory/lab/project/elective), credits | **Identity not tied to typed code** (F2); credits stored for a later credit-weighted roll-up |
| `CourseCode` | course, code, valid_from, valid_to, department | Many codes per course (typos fixed, twin codes like `UI21…`/`UII21…`) |
| `CourseGroup` | name, kind (open-elective group, twin-course group) | Links options of one elective row and CSE/AIML twins (F3) |
| `CourseOffering` | course, term, coordinator | One course taught in one term; may serve **several programmes** (e.g. a common course for CSE and CSE-AIML) |
| `Section` | offering, name (A, B, AIML), **programme, batch** | All sections share the offering's question paper; results are produced per section, per offering and **per programme** (only that programme's sections), so CSE and CSE-AIML batch roll-ups stay separate (open item 11) |
| `FacultyAssignment` | user, offering, section (nullable = all) | Limits lecturer access |

### 5.2 Students and roster
| Entity | Key fields | Notes |
|---|---|---|
| `Student` | internal id, name, college, status (active, withdrawn, detained, graduated) | Never created to fill gaps |
| `BatchMembership` | student, batch, from, to, reason | A detained student who joins the next batch keeps both periods (open item 7) |
| `StudentIdentifier` | student, kind (roll_no, hall_ticket, university_reg, erp_id), value, valid_from, valid_to | Roll number is just a label; can change; alphanumeric (`1602-23-748-001`) |
| `SectionMembership` | student, section, from, to, reason | Section changes keep history |
| `Enrolment` | student, offering, section, status (enrolled, withdrawn, exempted), dates | "Not enrolled" ≠ "enrolled with no mark". The enrolment's section decides where the student's marks count; `SectionMembership` is only the student's home section history |
| `ScriptMapping` | assessment, script_no, student, source, imported_by | SEE script numbers joined to students (exam branch) |

Uniqueness: `(college, kind, value, valid period)` for identifiers; same roll number in two sections of different years is allowed because uniqueness is scoped (scenario 4).

### 5.3 Outcomes
| Entity | Key fields | Notes |
|---|---|---|
| `ProgrammeOutcome` | programme, kind (PO / PSO / PEO), code (PO1…PO12, PSO1…, PEO1…), text, version, effective period | PEOs stored for reports (F4); not calculated in release 1 |
| `CourseOutcome` | course (definition version), code (CO1…), text, unit list | Courses with 4 COs supported |
| `CourseDefinitionVersion` | course, version, effective from/to | COs and mapping are versioned per course |
| `COPOMap` | co, po, strength (1, 2, 3, **0**), or no row = **not mapped** | Blank ≠ 0 (R18) |
| `Target` | scope (course offering / programme PO), value, source (set, revised by rule), rule used, approved_by | Per course per year; PO targets per programme/batch |

### 5.4 Assessments and marks
| Entity | Key fields | Notes |
|---|---|---|
| `AssessmentType` | college, name (Internal-I, Quiz…), behaviour (question_wise, per_student_average, single_total) | Defined in the method (section 6) |
| `Assessment` | offering, type, name, date, max_total, status (draft, open, submitted, approved, locked) | One per offering (shared across sections) |
| `Question` | assessment, number ("11"), max, choice_group, order | |
| `QuestionPart` | question, label ("a"), max, co (or "all COs"), **pass_mark_override + reason + approved_by** (nullable) | Marks and CO tags live at part level (finding 2.2.4); override entered by the coordinator, approved by IQAC |
| `ChoiceGroup` | assessment, questions, rule (best N; best K parts per question), missing_counts_as (0 / excluded) | Q11 to Q17 best 5; Q17 best 2 parts; Internal-II Q1 to Q6 best 4. A question in a choice group is a **choice question** for the denominator rule; all others are compulsory |
| `MarkSheetRow` | enrolment, assessment, **attempt** (regular / supplementary / improvement), status (not started, entered, submitted) | Tells "not entered yet" apart from "entered, part left blank"; which attempt counts is a method setting (default: regular only) |
| `MarkCell` | sheet row, part, **state**, value (numeric 6,2), entered_by, entered_at, source (manual / import id), row version | One row per student × part × attempt; the version number stops two people overwriting each other (optimistic locking) |
| `MarkChange` | mark_cell, old_state, old_value, new_state, new_value, by, at, reason, import_id | Append-only (F9) |

Mark states (R24): `value` (including 0), `blank`, `absent`, `withheld`, `exempted`, `not_applicable`, `not_attempted`. Zero and blank are never merged.
- Once a row is **entered**, an empty cell in a choice part means `not_attempted` (the workbook's convention: 281 blanks in Internal-II). An empty cell in a compulsory part is shown as a warning before submit. Its effect follows the tool's `Denominator` setting: with `enrolled` it counts as not passing (as Internal-I does in the workbook: /67 despite blanks); with `attempted` it is left out.

### 5.5 Methods, results, quality
| Entity | Key fields | Notes |
|---|---|---|
| `Method` | college (or university, or platform template), name ("Vasavi OBE R22") | |
| `MethodVersion` | method, version no., config JSON (validated), effective_from/to, status (draft, active, retired), approved_by, content hash | Immutable once active (scenario 14) |
| `MethodAssignment` | scope (college / department / programme / course), method_version, from, to | Inheritance and exceptions (section 7) |
| `CalculationRun` | scope (section / offering / programme / batch), method_version, engine_version, input_hash, started_by, at, status (provisional / complete), outputs JSON, trace JSON | Every run kept |
| `ResultValue` | run, entity (CO / course / PO), key, value (exact), display value, level, flags | Queryable result rows |
| `Override` | result key, original value, new value, reason (required), by, approved_by, at | Original never lost (R10, F20) |
| `SignOff` | run, step (faculty, HOD, director), by, at, comment, document hash | Signed run is frozen (F19) |
| `Observation`, `ActionPlan`, `ActionTaken`, `Evidence` | offering, text, owner, due date, done date, files | Last year's plan linked to this year's action taken (F17) |
| `ImportBatch` | kind, file (kept), uploaded_by, status (previewed, committed, rejected), error report | Source of every imported value (F8) |
| `HistoricResult` | programme, batch, kind (PO direct / total, course CO), key, value, source file | Earlier batches (2019-23, 2020-24) that were never calculated in the app, for the three-batch comparison (R23) |
| `StoredFile` | owner record, name, type, size, hash, storage location | Proof pages and signed PDFs; size cap per file (5 MB) and per college; storage backend switchable (database on demo, disk or bucket when self-hosted) |
| `AuditEvent` | college, actor, action, entity, entity_id, before, after, reason, ip, at, hash_prev, hash | Append-only, hash-chained (section 12) |

---

## 6. Calculation engine

### 6.1 Principles
1. **Pure and deterministic:** same input snapshot + same method version + same engine version → same output, byte for byte.
2. **Exact arithmetic:** Python `Decimal` with 28+ digits; PostgreSQL `numeric`. No floats anywhere in the calculation path.
3. **Full precision inside, rounding only where the method says** (default: final displayed values; R4).
4. **Every number explains itself:** each step writes a trace entry (inputs, rule, counts, denominator, exclusions, output).
5. **Nothing typed:** levels and counts are always computed (F11). Human changes happen only as overrides on top, with reasons.
6. **Configurable structure, not only numbers:** a method is a graph of steps from a fixed catalogue.

### 6.2 Pipeline (default shape)
```
 MarkCells ──► [per assessment] ──────────────────────────────────────────┐
   1 Normalise states       (absent→0 or excluded, per tool)              │
   2 ChoiceSelect           (best N questions, best K parts)              │
   3 Behaviour step:                                                      │
      question_wise:  QuestionPass → Denominator → %/part → CO average    │
      per_student_average: average per student → pass → % of class       │
      single_total:   total → pass → % of class                           │
   4 Bands → level per CO   (flag below lowest band)                      │
                                                                          ▼
 [per CO]  5 MergeTool (e.g. Internal = average of Int-I and Int-II levels where both cover the CO)
           6 Combine direct (weights per tool: 0.30 / 0.05 / 0.05 / 0.60)
           7 Combine final  (0.8 direct + 0.2 indirect; indirect = entered value until surveys)
 [section → offering] 8 RollUp sections (stage configurable; default: average of section CO attainment)
 [course]  9 CourseAttainment (average of COs present; blanks ignored)
          10 TargetCompare (which value is compared: unrounded / truncated / rounded)
          11 CO→PO/PSO (Σ map×CO / Σ map over mapped COs; 0 handled per setting)
 [batch]  12 BatchRollUp (simple average of course PO values over all terms; equal weight)
          13 Combine batch total (0.8 direct + 0.2 indirect PO)
          14 PO TargetCompare
          15 Counts (courses attained / not, core / non-core)
 Every step → trace
```

### 6.3 Step catalogue (release 1)
| Step | Parameters | Covers |
|---|---|---|
| `NormaliseStates` | per state: `zero`, `exclude`, `error` | R24, quiz absent = 0 |
| `ChoiceSelect` | groups, best_n, best_k_parts per question, tie rule (lower question number first), missing_counts_as | 7.3.1, scenario 8. Note: "missing counts as 0" only has an effect in **student-total** methods. In the per-part method a missing 5th answer belongs to no part and no CO, so it cannot change any CO percentage; the engine records it as a note (confirmed by synthetic test T3) |
| `QuestionPass` | pass_pct (60), boundary (`>=` / `>`), per-part override (value + reason) | R1, R2, finding 2.2.1 |
| `Denominator` | per question: `by_choice` (**default, decided**: choice question → students who attempted it; compulsory question → everyone who sat the assessment), or `attempted`, `sat`, `enrolled`, `fixed_list`; plus `whole_assessment_absent`: `exclude` (default; matches "only SEE-attempted students count") or `count_as_fail` | R6, decision 3. "Sat" = has an entered mark-sheet row and is not marked absent for the whole assessment |
| `AggregateToCO` | `mean_of_question_pct` (default), `marks_weighted`, `student_level` (student passes CO if ≥ X% of CO marks) | R7 + other colleges' methods |
| `PerStudentAverage` | items, max, pass_pct, boundary, absent rule, applies_to (`all_cos` / list) | Quiz, assignment |
| `SingleTotal` | max, pass mark, applies_to | Lab |
| `Bands` | ordered list of (min %, level, label), below_lowest: `flag` plus **value used in later steps** (`block` = result provisional until someone reviews, `0`, or a set value) | R8, below 10% flagged. Without the second setting the weighted sum has no input (gap found in review) |
| `MissingData` | what to do when a tool gives no value for a CO (no part tagged, or nobody attempted): `renormalise` the other weights, use `0`, or `block` | Gap found in review (synthetic test T8) |
| `MergeTools` | method: `average`, `max`, `latest`, weights | R9. The merged level may be fractional (L3 and L2 give 2.5); reports print it as 2.5, not a rounded level |
| `WeightedCombine` | weights by tool (must sum to 1; validated) | R11, R12 |
| `RollUp` | from → to, method (`mean`, `weighted by students`, `credit weighted`), stage (`pct`, `level`, `attainment`) | R16, R20 |
| `Average` | ignore blanks (default) | R13 |
| `MapToOutcomes` | formula `weighted_mean` (default); if every mapped CO has strength 0, the PO is `blank` (default) or `0` | R17 to R19. A 0 strength adds nothing to the weighted mean, so the only case where 0 and blank differ is "all zeros"; the batch average skips blanks but counts zeros (the batch file has corrections to 0, e.g. Semiconductor Physics PO10) |
| `Precision` | **per level** (question %, CO, course, PO, batch): mode `truncate` (default) or `round` (half away from zero, same as Excel ROUND), places; `compare_with`: `unrounded` (default) or `displayed` | R3, R4, decision 2. Python's default decimal rounding is "half to even" (2.845 → 2.84, Excel gives 2.85), so the engine always sets the mode explicitly (test T9). Bands always use the unrounded %; if the displayed % looks like a band edge (e.g. shows 60.00 but is 59.996 and gets Level 2), the report shows a marker and the full value |
| `TargetCompare` | operator (`>=`), near-target warning margin | R14, F16 |
| `TargetRevise` | rule: `manual` (**default, decided** until the rule is known), `add_points(x) if met`, `add_percent(x) if met`, `multiply(x) if met`; if not met: `keep` / `lower`; floor/ceiling; start value | R15 (rule still open with the mentor) |
| `IndirectInput` | source: `entered_value` (now; entered by IQAC per course CO and per programme PO, with a source note), later `survey` | 5.3. While the value is entered, reports label it "entered, not measured" and also show **direct-only** attainment, so a typed 3 cannot hide a weak direct result (risk in requirements section 19) |
| `CountStatus` | group by category (core / non-core) | R23 |
| `BatchInput` | which course result feeds the batch: the **signed** run (default) or the latest run | A batch report never mixes signed and unsigned course values without saying so |

A new college whose method needs something not in this list gets a **new step type in a product release** (tested, versioned), never custom code per college. That is the price of safety, and it is stated in the documentation.

### 6.4 Method config example (Vasavi, abbreviated)
```json
{
  "schema": "attainment-method/1",
  "name": "Vasavi OBE (theory)",
  "levels": {"bands": [[60, 3, "L3"], [50, 2, "L2"], [10, 1, "L1"]], "below_lowest": {"flag": true, "value_for_calc": "block"}},
  "missing_data": "block",
  "attempts": "regular_only",
  "precision": {"default": {"mode": "truncate", "places": 2}, "batch": {"mode": "truncate", "places": 2}, "compare_with": "unrounded"},
  "tools": {
    "INT1": {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">=", "denominator": "by_choice"},
    "INT2": {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">=", "denominator": "by_choice",
             "choice": {"groups": "from_paper", "best_n": 4}},
    "SEE":  {"behaviour": "question_wise", "pass_pct": 60, "boundary": ">=", "denominator": "by_choice",
             "whole_assessment_absent": "exclude",
             "choice": {"groups": "from_paper", "best_n": 5, "best_k_parts": {"17": 2}, "missing": "note_only"}},
    "QUIZ": {"behaviour": "per_student_average", "items": 3, "max": 5, "pass_pct": 60, "absent": "zero", "applies_to": "all_cos"},
    "ASSIGN": {"behaviour": "per_student_average", "items": 3, "max": 5, "pass_pct": 60, "absent": "zero", "applies_to": "all_cos"}
  },
  "merge": {"INTERNAL": {"from": ["INT1", "INT2"], "method": "average"}},
  "direct": {"INTERNAL": 0.30, "ASSIGN": 0.05, "QUIZ": 0.05, "SEE": 0.60},
  "final": {"direct": 0.8, "indirect": 0.2, "indirect_source": "entered_value"},
  "sections": {"rollup": "mean", "stage": "co_attainment"},
  "course": {"aggregate": "mean_ignore_blank", "target_compare": ">="},
  "po": {"formula": "weighted_mean", "all_zero": "blank"},
  "batch": {"rollup": "mean_over_courses", "weights": "equal", "final": {"direct": 0.8, "indirect": 0.2}},
  "targets": {"revise": {"rule": "manual"}}
}
```
- The lab method is a second, smaller config (`SingleTotal` 30 marks, pass 18, applies to all COs, final = direct, no indirect).
- Per-part pass-mark overrides (e.g. 2 for Internal-II 3.5-mark parts) live on the question paper, not in the method, because they belong to one paper.
- Validation (Pydantic) rejects: weights not summing to 1, bands overlapping or unordered, references to tools that do not exist, missing CO tags, percentages outside 0 to 100.

### 6.5 Explanation trace (F12, R25 to R27)
Each output value links to a trace like:
```
SEE · CO2 · 51.06%  → Level 2 (band 50 to <60)
  = mean of 5 parts tagged CO2:
    Q3   31/66 = 46.96%   (attempted 66 of 66)
    Q4   51/66 = 77.27%
    Q12a 21/50 = 42.00%   (attempted 50 of 66 · attempt rate 75%)
    Q12b 29/52 = 55.76%
    Q16b 16/48 = 33.33%
  pass mark: 60% of max (2.4 of 4), boundary >=
  exclusions: none in these parts (script 11's Q17 dropped by best 5 of 7 affects CO3 to CO5)
  method: Vasavi OBE v3 · engine 1.0.0 · input hash 9f3c…
```
- Small-group warning when a denominator is below a set number (default 10) (R26).
- Attempt rate beside every attempted-only percentage (R27).

### 6.6 When calculations run
- **Automatically** after any save of marks, mapping, target or method assignment, for the affected section/offering (milliseconds at our size).
- **On demand** for batch and department roll-ups (button + cached latest run).
- **Run storage:** automatic runs replace the one "latest" run per scope (so autosaves do not create thousands of rows); a run is kept permanently at submit, approve and sign, and when someone presses "Save snapshot".
- **Never** for signed runs: a signed run is frozen; later changes create a new run that shows as "differs from signed" (scenario 20).

### 6.7 Provisional vs complete (F14)
A run is **complete** only if: every enrolled student has a mark-sheet row with status **entered** for every required assessment (blank choice parts are normal and do not count as missing), no value is `block`ed by `Bands` or `MissingData`, the method version is active, and the CO-PO map and target exist. Otherwise **provisional**, with a checklist of what is missing. Provisional results are watermarked on every report.
- (v1.0 said "every part must have a state"; that would have made every SEE run provisional, because unchosen questions are always blank.)

### 6.8 Overrides (R10, F20)
- A result stopped for review (`Bands` below 10%, or `MissingData`) is released only by an authorised person who enters the value to use, with a reason. This is recorded as an override, so it shows on reports.
- Override = new value on a specific result key, with mandatory reason, by an allowed role, optionally needing approval.
- The original computed value is kept and shown ("2 → 3, overridden by HOD on 12 Mar: reason …").
- Downstream steps use the overridden value; the trace shows both.
- Overrides are allowed until the result is approved. After that, an override needs a reopen (8.7), so a signed result never changes silently.

### 6.9 Engine versioning
- The engine has its own version number (semantic versioning). Every run stores it.
- A golden test suite (section 16) must pass before any engine release. A change that alters any golden output needs a written reason.
- **Method schema versions:** each config says which schema it uses (`attainment-method/1`). When the schema changes, the engine keeps reading old versions (or a tested converter upgrades them), so a 2025-26 method still runs in 2028.
- **Recalculating old terms after an engine upgrade:** signed runs are never touched. Unsigned runs are recalculated; if a value changes, the change is listed for the coordinator before it replaces the old run.

---

## 7. Configuration management

### 7.1 Scopes and inheritance (section 8 "scope of settings")
```
 Platform templates (e.g. "NBA common", "Vasavi OBE")
   └─ University method (weights, bands: same for all departments)
        └─ College (may adopt university method as-is)
             └─ Department / Programme (exceptions only, if allowed)
                  └─ Course (exceptions only: e.g. lab method, per-question pass mark)
```
- The most specific assignment wins; the effective method is resolved at calculation time and **stored in the run**.
- Each level can lock settings so lower levels cannot change them (e.g. university weights).

### 7.2 Versioning and effective periods
- Methods are edited as **drafts**. Activating a draft creates an **immutable version** with `effective_from` (a term or date).
- Old terms keep their version; new terms use the new one automatically (scenarios 14, 17).
- Changing the method for a term that already has signed results is blocked; for unsigned results it asks for a reason and reruns.

### 7.3 Safe editing
- **Guided setup wizard** for the configuring user: start from a template, answer plain-language questions ("Is a mark exactly at 60% a pass?"), see the generated config.
- **Dry run / diff:** before activation, run the new version on last term's data and show what changes (e.g. "Deep Learning course 2.32 → 2.18, status flips").
- **Approval:** activation requires the IQAC role (and optionally the principal).

---

## 8. Workflows

### 8.1 Onboard a college (platform admin, once)
1. Create college, link to university, choose a method template.
2. Create the college admin account; admin receives a set-password link.
3. College admin creates departments, programmes, batches, terms (or imports them from Excel).

### 8.2 Prepare a term (college admin + coordinators)
1. Import roster per batch/section (any roll-number format; gaps allowed). Preview shows new, changed, missing students.
2. Create course offerings for the term; assign faculty per section.
3. Coordinators confirm COs and CO-PO map (copied from the last version; edit creates a new version).
4. Targets: the system proposes this year's target from last year's result and the revision rule; coordinator confirms.

### 8.3 Set up an assessment (coordinator)
1. Choose assessment type (Internal-I…), enter question paper: questions, parts, max marks, CO per part, choice groups.
2. Or copy from last year's paper and edit.
3. The system checks: total max, every part tagged, choice rules valid. Then opens it for marks entry.

### 8.4 Enter marks (lecturer)
```
 Open my section ─► grid (rows = students, columns = parts) ─► type or paste
      │                     │ cell checks: number ≤ max, state codes (AB, -, NA)
      │                     ▼
      │              Save draft (auto every 30 s) ─► Submit ─► coordinator review
      └─► or Download template ─► fill in Excel ─► Upload ─► preview errors ─► Confirm
```
- Keyboard shortcuts: `AB` absent, empty = blank, `-` not attempted.
- Row-level errors in plain words ("Q12a: 5 is above the max of 4").
- Lecturers see only their assigned sections (F6).
- Two people saving the same cell: the second save is refused with "changed by X at 10:42, reload" (row version). An import locks the assessment for the few seconds of its commit.

### 8.5 SEE marks (exam branch)
1. Exam branch uploads the script-number → student mapping (or the system generates script numbers).
2. Uploads SEE marks keyed by script number; the system joins to students and reports unmatched or duplicate scripts before commit.

### 8.6 Calculate and review (automatic + coordinator)
- Results update automatically; status shows provisional/complete.
- Coordinator reviews the course result page: per-tool levels, CO, course, PO, flags, explanation.

### 8.7 Approve, sign, freeze (lecturer → coordinator → HOD → principal)
```
 per section, per assessment:   draft ─► submitted (lecturer) ─► accepted (coordinator)
                                            ▲            │
                                            └─ returned for correction (coordinator, reason)
 per offering (course result):  reviewed (coordinator) ─► approved (HOD) ─► signed (principal)
                                     ▲                                          │
                                     └──── reopen (HOD/IQAC, reason, new version) ◄┘
 per programme + batch:         prepared (IQAC) ─► approved (HOD) ─► signed (principal)
```
- The course result can be reviewed only when every section's assessments are accepted.
- The batch report is frozen at sign-off like a course result, and records which signed course runs it used.
- At **approved**, marks lock (F10). At **signed**, the run is frozen and the PDF is generated with a document hash.
- "Signing" in the app is an approval record (name, role, time). The PDF prints these and leaves space for wet signatures; legally valid digital signatures (DSC) are not in release 1.
- Reopen creates a new run and a new signature cycle; the old signed version stays readable.

### 8.8 Override (authorised role, before approval)
Open a result → Override → new value + reason → (approval if configured) → recorded and shown on reports.

### 8.9 Quality loop (lecturer, HOD)
1. After results: lecturer writes observations and an action plan per course (gaps pre-filled from the gap view: COs below target, weak questions).
2. Next year: the plan appears on the same course's new offering; lecturer records actions taken with dates and uploads proof.
3. Action Taken Report generated.

### 8.10 Department and batch results (IQAC, HOD)
1. Choose programme + batch (e.g. CSE 2021-25). The system collects all offerings of that batch across 8 semesters.
2. Runs the batch roll-up; shows direct, indirect, total, targets, status; compares with earlier batches; counts attained courses by core/non-core.
3. Each section carries its programme and batch, so the roll-up takes only that programme's sections (CSE and CSE-AIML stay separate even in a shared offering).
4. Backlog/detained students: rule configurable (open item 7); default: a student counts in the section where they are enrolled, and that section's batch.

### 8.10a Indirect values (until surveys exist)
- IQAC enters the indirect value per course CO and per programme PO (3 in the reference), with a source note ("entered, not measured"). Results stay provisional until it is entered.

### 8.11 Year end
- Target revision proposal per course (rule from method), reviewed by coordinator, approved by HOD.
- Method changes for next year as a new version.

### 8.12 Reminders
- In-app task list on the home page (marks due, approvals waiting). Email reminders are a "should" (they need a working mail service; see 14.5).

### 8.13 Import historic Excel and compare (F22)
- Upload an old workbook's values (CO levels or course PO values) → the system computes from marks (if available) → side-by-side table with differences highlighted.
- Earlier batch totals with no marks in the system (2019-23, 2020-24) are imported as `HistoricResult` rows so the three-batch comparison works from day one.

---

## 9. Roles and permissions

Roles are assigned **with a scope** (college, department, programme, offering, section). One user can hold several.

| Action | Platform admin | College admin | IQAC | HOD | Coordinator | Lecturer | Exam branch | Principal | Auditor |
|---|---|---|---|---|---|---|---|---|---|
| Create college, platform templates | ✔ | | | | | | | | |
| Users, roles, structure, roster | | ✔ | | | | | | | |
| Method edit / activate | | | ✔ / ✔ | view | view | | | view | view |
| COs, CO-PO map, targets | | | ✔ | approve | ✔ | view | | view | view |
| Question paper | | | | | ✔ | view | | | view |
| Enter internal marks | | | | | own | own sections | | | |
| Enter SEE marks, script map | | | | | | | ✔ | | |
| Submit / accept or return / approve / sign | | | prepare batch | approve | accept, return, review | submit | | sign | |
| Override with reason | | | ✔ | ✔ | per setting | | | | |
| Reopen locked data | | | ✔ | ✔ | | | | | |
| Observations, action plans | | | view | ✔ | ✔ | ✔ (own) | | view | view |
| Reports, exports | | ✔ | ✔ | dept | course | own | | ✔ | ✔ (read-only) |
| Audit log | platform | college | college | dept | | | | college | college |

- Platform admin **cannot read student marks** by default (support access needs a time-limited grant from the college admin, logged).
- Not every college uses every role; one person may hold several (e.g. coordinator = lecturer).
- "Principal" and "director" are the same role (the head of the college signs).

---

## 10. Screens and usability

### 10.1 Screen list
| Area | Screens |
|---|---|
| Home | Role-based dashboard: my tasks (marks due, approvals waiting), status of my courses |
| Setup | Structure (departments, programmes, batches, terms), courses and codes, offerings and sections, faculty assignment, roster (with import), users and roles |
| Outcomes | COs per course, PO/PSO per programme, CO-PO map grid (with blank vs 0), targets |
| Method | Template picker, guided wizard, version list, diff/dry-run, activation |
| Assessments | Question paper editor (questions, parts, CO tags, choice groups) |
| Marks | Section grid, import with preview, change history per cell, submit |
| Results | Section and course result page with explain panel; department and batch page; gap view |
| Quality | Observations, action plans, actions taken with proof uploads |
| Approvals | Inbox per role; sign-off page |
| Reports | Report list with filters; download PDF/Excel |
| Admin | Audit log viewer, imports log, backups status (platform) |

### 10.2 Usability rules (objective 7, "lecturers without training")
- Lecturer path is three clicks: Home → My section → Grid.
- The grid looks like their Excel sheet (same column order as the question paper).
- Plain English errors; never a stack trace.
- Every result number is clickable for "how was this calculated".
- Works on a 1366×768 laptop; viewing works on phones.
- English UI first; texts kept in translation files (Django i18n) for later languages.
- Accessibility: keyboard use, labels, contrast (WCAG 2.1 AA as a target).

---

## 11. Import, export and reports

### 11.1 Imports (F6, F8, F22, scenario 18)
| Import | Key used | Checks |
|---|---|---|
| Roster | roll number + batch + section | duplicates, format, students missing vs last import |
| Marks (internal) | roll number within section | unknown roll, above max, invalid state code, duplicate row |
| SEE marks | script number via mapping | unmapped scripts, two scripts for one student, more answers than the choice rule allows (warn, then apply best N) |
| Course structure, COs, CO-PO map | course stable id or code alias | unknown course, map value not in {blank, 0, 1, 2, 3} |
| Historic results | course + term | for comparison only |

Flow: upload → parse (openpyxl) → validate all rows → preview (green / errors) → **commit only valid rows in one transaction, or all-or-nothing** (setting; default all-or-nothing for marks) → file kept with the import record.
- **Parsing rules learned from the mentor's files:**
  - Map columns from the question paper and the app's own template, not from header text (Internal-II has parts with no header label).
  - Read cached values only (formulas are not evaluated). If a cell has a formula but no cached value, reject the file and say "open and save it in Excel first".
  - The mentor's batch workbook makes openpyxl fail on its chart XML; the importer removes charts and drawings from a copy and retries.
  - Install `defusedxml` so openpyxl is protected against malicious XML.

### 11.2 Templates and exports
- Downloadable, pre-filled Excel templates per section/assessment (roll numbers and question columns already in place).
- Every screen table exports to Excel.
- Full college data export (Excel + JSON) for portability and data requests.

### 11.3 Reports (section 12 of requirements)
| Report | Format | Content |
|---|---|---|
| Per-assessment CO attainment sheet | PDF, Excel | max marks, students ≥ 60%, %, level per CO (assignment, quiz, lab, internals, SEE) |
| Theory course CO attainment analysis | PDF | levels per tool per CO, direct, indirect, final, course attainment, target, status, observations, action plan, signature blocks |
| Lab course attainment analysis | PDF | |
| CO-PO/PSO table | PDF, Excel | CO attainment, mapping, course PO row |
| Action Taken Report | PDF | last year's plan, actions with dates, proof pages |
| Department/batch report | PDF, Excel | CO attainment by course and semester, PO/PSO per course, batch direct/indirect/total, targets, three-batch comparison chart, attained counts core/non-core, list of overrides/corrections |
| NBA flat course list | Excel | one row per course |
| Explanation appendix | PDF | trace for any selected number |

Every report footer: college, programme, batch, course, term, **method version**, engine version, run id, data status (provisional/complete), generated at, document hash.
Reports are HTML templates (one per report, per college if needed) rendered on screen and to PDF by WeasyPrint. A college can get its own layout by adding a template (product change, not code per calculation).

---

## 12. Audit trail, versions, locking
- **Audit log:** every create/update/delete of business data, every login, import, override, approval, method change, export of personal data. Fields: who, when, what, before, after, reason, IP.
- **Tamper evidence:** each audit row stores a hash of itself plus the previous row's hash (per college). Writes for one college are serialised with a PostgreSQL advisory lock so two requests cannot both claim the same previous row. A nightly job verifies the chain and alerts on a break.
- **Audit and deletion:** audit rows refer to students by internal id, never by name or roll number, so anonymising a student later does not break the hash chain.
- **Append-only:** the app's database user cannot update or delete audit rows (PostgreSQL grants + trigger).
- **Mark history:** `MarkChange` rows for every change (F9); reason required after submission.
- **Record history:** django-simple-history on setup tables (courses, COs, mappings, targets).
- **Locks:** per assessment and per offering, from the workflow state (section 8.7). Locked data rejects writes at the service layer and by a database check.
- **Reproducibility:** each run stores the input hash; re-running with the same inputs must give the same hash of outputs (tested nightly on a sample).

---

## 13. Security, privacy, multi-college isolation

### 13.1 Isolation between colleges (F23, scenario 19)
1. **App layer:** middleware sets the current college from the logged-in user; all tenant models use a manager that always filters by `college_id`; a model without `college_id` fails a test.
2. **Database layer:** PostgreSQL row-level security on every tenant table: `USING (college_id = NULLIF(current_setting('app.college_id', true), '')::uuid)`. Implementation rules (each one prevents a known leak):
   - Every request runs in a transaction (`ATOMIC_REQUESTS = True`) and sets the college with `SET LOCAL`, so the value dies with the transaction and cannot leak to the next request on a reused connection. This also works through Neon's connection pooler.
   - If no college is set, the policy matches nothing (fail closed).
   - The web app connects as a role that is **not** the table owner and has no `BYPASSRLS`. Only migrations and the platform backup use a separate owner role.
   - Management commands and scheduled jobs must set the college explicitly; a helper does it and a test checks every command.
3. **Tests:** an automated test creates two colleges and tries every list/detail/export endpoint as the wrong college; any leak fails the build.
4. **Files:** stored under `/<college_id>/…`, served only through the app with a permission check.

### 13.2 Application security
- Passwords hashed with Argon2; minimum length 10; breached-password check optional.
- Optional TOTP two-factor for admin, IQAC, HOD (django-otp); recommended for platform admin.
- Session cookies: Secure, HttpOnly, SameSite=Lax; session timeout 30 min idle.
- CSRF protection (Django built in); HTMX sends the CSRF token.
- Login rate limiting (django-axes); lockout after repeated failures.
- HTTPS only (HSTS).
- Uploaded files: imports up to 10 MB (.xlsx/.csv); stored proof files up to 5 MB (.pdf/.jpg/.png); type checked by content, never executed.
- Password reset by email; where a college has no working email, the college admin can issue a one-time reset link (logged).
- Dependency scanning (GitHub Dependabot, free), secret scanning; no secrets in the repo (environment variables).
- Security headers (CSP, X-Frame-Options) via django-csp.

### 13.3 Privacy (India DPDP Act 2023 and DPDP Rules 2025)
- **Timing:** the DPDP Rules were notified on 14 Nov 2025. Most duties (notice, security safeguards, breach reporting, children's consent, data principal rights) apply from **14 May 2027**, which is likely during or soon after the pilot. Build for them now.
- **Roles:** the college is the **data fiduciary**; whoever hosts for them is a **data processor**. Security duties also apply to processors, and the fiduciary must put security terms in its contract with the processor. When we host, a short data-processing agreement is needed; when the college self-hosts, the college holds everything.
- **Logs:** the Rules require keeping processing logs for at least **one year**. Application logs therefore keep 14 days of detail, but the audit log (who saw or changed what) is kept for at least a year (longer as the college decides).
- **Students under 18:** some first-year students may be 17. The Rules require verifiable parental consent for children's data, with exemptions for some purposes and some classes of fiduciaries listed in a schedule. **Whether a college's academic records are exempt is not confirmed: ask the college's legal or IQAC office before the pilot.** The design keeps no data beyond what the college already holds for exams.
- **Minimise:** store only name, identifiers, batch, section, marks. No phone, address, Aadhaar, date of birth.
- **Notice:** a privacy notice the college can show students (template provided).
- **Access and correction:** college admin can export or correct a student's records.
- **Retention:** configurable per college (accreditation needs several years); deletion/anonymisation tool for students beyond retention. The Rules ask for notice to the person at least 48 hours before deletion; the tool lists affected students and waits before deleting.
- **Breach handling:** documented steps, contact person, audit log to establish what was accessed; the Rules require informing the Data Protection Board and the affected students without delay.
- **Development data:** anonymised copies only (roll numbers and names replaced), generated by a script; real data never leaves the college's environment for development (open item 16).
- **Hosting region:** prefer India or the nearest region offered; record the region in the college's data agreement.

---

## 14. Hosting, deployment, backups, operations

### 14.1 Environments
| Environment | Purpose | Where | Data |
|---|---|---|---|
| Local | Development | Student laptops, `docker compose up` | Synthetic/anonymised |
| CI | Tests on every push | GitHub Actions | Synthetic |
| Demo | Mentor reviews, presentations | **Render free web service + Neon free PostgreSQL** | Anonymised Vasavi data |
| Pilot / production | Real use by a college | **College server or VM (Docker)**; alternative: Oracle Always Free VM if a card is available | Real |

### 14.2 Free-tier facts that shape this (checked 2026-11-06; re-check before use)
- **Render free web:** sleeps after 15 min idle, ~1 min to wake, 750 h/month, disk wiped on restart → store nothing on disk. Fine for demo, not for exam-week use.
- **Files on the demo:** stored in the database with a 5 MB per-file cap and a per-college quota, because Neon free has 1 GB per project; marks data needs well under 100 MB, so proof pages are the only real risk.
- **Render free PostgreSQL is deleted 30 days after creation → do not use.**
- **Neon free:** 1 GB per project (we need well under 100 MB per college-year), scales to zero after 5 min (wakes in under a second), only 6 h restore history → **our own nightly backups are required**.
- **Supabase free** pauses after 1 week idle (semester breaks) → not chosen.
- **Self-hosting** has no limits and keeps student data in the college → chosen for real use.

### 14.3 Deployment
- One Docker image (app + Gunicorn); `docker-compose.yml` with app, PostgreSQL, Caddy (HTTPS), backup job.
- Configuration by environment variables (database URL, secret key, allowed hosts, email settings).
- Migrations run automatically on deploy; rollback = previous image + restore backup.
- **Updating a self-hosted college:** `./update.sh` takes a backup, pulls the new image tag, runs migrations and checks `/healthz`; release notes say whether results can change. Colleges stay at most two minor versions behind (supported window).
- **HTTPS:** demo uses the host's free subdomain and certificate. A college server with a public domain uses Caddy's free certificates; a server reachable only inside the campus network uses Caddy's internal certificate authority, installed once on staff machines.
- GitHub Actions: on push → lint, type-check engine, tests, build image; on tag → publish image to GitHub Container Registry (free for public); demo auto-deploys from `main`. Database URL and backup key are GitHub secrets, never in the repository.
- **Memory on the free demo (512 MB):** charts in PDFs are drawn as SVG on the server, and the largest report (batch, 8 semesters) is tested on the demo before the mentor review.
- Release notes per version, including any engine change and its effect on golden results.

### 14.4 Backups and recovery (section 13 "official marks")
| Item | Plan |
|---|---|
| What | Full `pg_dump` + uploaded files |
| When | Nightly; plus before every deploy and before every sign-off batch |
| Where | **Demo (Neon):** a GitHub Actions job dumps and encrypts (age) to a private store; demo data is anonymised only. **Self-hosted:** a backup container on the college server dumps nightly to a second disk and copies off-site (college Google Drive or another college machine). GitHub Actions cannot reach a server inside a college network, so it is not used there |
| Keep | 7 daily, 4 weekly, 12 monthly |
| Targets | Lose at most 1 day of data (RPO 24 h); restore within 4 hours (RTO 4 h) |
| Test | Automated monthly restore into a scratch database + row counts + golden recalculation; manual restore drill each term |
| Encryption key | Held by the college admin, with a sealed copy kept by the principal's office; for the demo, by the team lead. A lost key makes every backup useless, so the restore drill also checks the key |
| Alert | healthchecks.io ping on backup success; email if missed |

### 14.5 Operations
- Health endpoint `/healthz` (DB reachable, migrations current).
- Uptime monitor (free), error tracking (Sentry free or GlitchTip).
- Structured logs (JSON) without personal data; 14-day retention.
- Email: SMTP through the college's mail or a free transactional plan; on Render free, outbound SMTP ports are blocked, so use an HTTP email API or skip emails in demo.
- Support runbook: reset password, reopen a locked assessment, restore a backup, onboard a college.

---

## 15. Integration readiness (later ERP)
- **Now (release 1):** documented Excel/CSV formats for every import/export; `external_id` on students, courses, faculty, offerings; integration code isolated in the `integration` module (adapters).
- **Release 2:** read-only REST API (Django REST Framework) with OpenAPI docs and per-college API keys; endpoints for results and statuses.
- **Later:** write API for rosters/marks, webhooks on sign-off, standards (IMS OneRoster for rosters/results, LTI for launching from Moodle), SSO via OpenID Connect/SAML (e.g. Keycloak or the college's Google/Microsoft).
- **Never:** direct reads from an ERP database.

---

## 16. Testing and acceptance

### 16.1 Test layers
| Layer | What | Tool |
|---|---|---|
| Engine unit tests | Each step type with edge cases: boundary at exactly 60%, `>` vs `>=`, truncate vs round, blanks vs zero vs absent, best 5 with ties, best 2 of 3 parts, below lowest band, empty denominator, 4-CO course | pytest |
| Golden tests | Mentor's Deep Learning workbook → Appendix A (prototype already passes); CSE 2021-25 batch → Appendix B direct values (this tests the roll-up only, since course values in that file are pasted); two published methods from other colleges (paper) | pytest with fixture files. **Fixtures are anonymised** (roll numbers replaced, names removed) because the workbooks hold real student data and the repository may be public |
| Decimal tests | The float trap found in review (CO1 = 2.52, not 2.51), the half-even trap (2.845 must round to 2.85), truncation and rounding at every precision setting | pytest |
| Property tests | Random marks: percentages within 0 to 100, levels within bands, adding a passing student never lowers a %, results identical on re-run | Hypothesis |
| Config validation tests | Invalid configs rejected with clear messages | pytest |
| Service/integration tests | Imports, workflow transitions, locks, overrides, versioning | pytest-django |
| Isolation tests | Cross-college access on every endpoint | pytest-django |
| Browser tests | Lecturer entry, import preview, sign-off, report download | Playwright |
| Performance | 10 colleges × 8 programmes × 4 years synthetic data; batch run < 5 s; grid of 130 students × 30 parts loads < 2 s | pytest-benchmark / locust (free) |
| Restore test | Monthly backup restore | GitHub Actions (demo); the local backup job (self-hosted) |

### 16.2 Acceptance scenarios (requirements section 15) mapped
| # | Scenario | Covered by |
|---|---|---|
| 1 | Reference course | Golden test. The fixture's question paper carries the college's typed Internal-II pass marks as overrides (reason: "as used by the college in 2025-26"); passing in the prototype (run J). A second golden test with no overrides expects 2.18, Not attained |
| 2 | Reference batch | Golden test (direct values passing in prototype) |
| 3 | Gaps, ranges, alphanumeric ids | Roster import tests |
| 4 | Same roll number in two sections | Identifier scoping test |
| 5 | Withdrawal / section change | Enrolment status + membership history tests |
| 6 | Blank vs zero vs absent | `NormaliseStates` tests |
| 7 | Boundary at exactly 60% | `QuestionPass` tests (prototype T4) |
| 8 | Best 5 of 7 with parts, Q17 best 2, 4 attempted → 0 for fifth | `ChoiceSelect` tests (prototype T1 to T3). "0 for the fifth" has no CO to land on in the per-part method; the test checks it is recorded as a note and changes nothing (see 6.3) |
| 9 | Shared CO across internals | `MergeTools` test |
| 10 | Quiz/assignment applies to every CO | `PerStudentAverage` test |
| 11 | Below 10% flagged | `Bands` test |
| 12 | Section roll-up | `RollUp` test |
| 13 | Override with role and reason | Service + report test |
| 14 | Config change applies to later periods only | Method versioning test |
| 15 | Incomplete data → provisional | Completeness test |
| 16 | Second method on paper | Golden test with a second config |
| 17 | Saved config reused next term | Method assignment test |
| 18 | Bad import | Import tests |
| 19 | Data isolation | Isolation tests |
| 20 | Signed report frozen | Sign-off test |

### 16.3 Real-world validation
- **Parallel run:** one full semester at Vasavi with Excel and the app side by side; every difference explained and classified (app correct / Excel quirk / rule unclear).
- **Mentor sign-off** on the rules guide before the pilot.

---

## 17. Code structure and conventions
```
attainment/
  config/                 Django settings (base, dev, prod), urls, wsgi
  apps/
    tenancy/ accounts/ academics/ roster/ outcomes/ assessments/
    marks/ methodology/ results/ quality/ reports/ imports/ audit/ integration/
      models.py  services.py  views.py  forms.py  templates/  tests/
  engine/                 pure Python package (no Django imports)
    model.py              data classes for inputs/outputs
    steps/                one file per step type
    pipeline.py           builds and runs the step graph
    precision.py          Decimal helpers (truncate, round)
    trace.py
    schema.py             Pydantic method schema
    tests/ golden/ (fixtures from mentor workbooks, anonymised)
  templates/ static/
  docker/ docker-compose.yml  Dockerfile  Caddyfile
  scripts/ anonymise.py backup.sh restore.sh
  docs/ user-guide/ rules-guide/ admin-guide/ adr/  (architecture decision records)
```
- Conventions: ruff formatting; type hints in `engine`; every pull request needs one review and green CI; decisions recorded as short ADRs in `docs/adr/`.
- Branching: `main` always deployable; feature branches; tags for releases.

---

## 18. Delivery plan

### 18.1 Phases (assumes 4 students, ~20 weeks to pilot)
| Phase | Weeks | Output | Exit check |
|---|---|---|---|
| 0. Foundations | 1 to 2 | Repo, Docker, CI, Django skeleton, tenancy + RLS, login, roles | Isolation test passes |
| 1. Engine first | 2 to 5 | Engine package with all release-1 steps, Pydantic schema, golden tests (Appendix A, B), property tests; find two published methods from other colleges for scenario 16 | Golden tests green; rules guide draft to mentor |
| 2. Setup data | 4 to 8 | Structure, courses + codes, offerings, sections, roster import, COs, CO-PO map, targets | Scenarios 3, 4, 5 pass |
| 3. Marks | 7 to 11 | Question paper editor, marks grid, Excel template + import, SEE script mapping, states, history | Lecturer test with 2 real lecturers |
| 4. Results | 10 to 14 | Calculation runs, explain panel, provisional, overrides, section/course/batch pages, gap view | Scenarios 1, 2, 6 to 15 pass end to end |
| 5. Workflow + reports | 13 to 17 | Approvals, locks, sign-off, PDFs in the college's layouts (copied from the mentor's report documents), Excel exports, NBA list, Action Taken Report | Scenario 20; reports reviewed by mentor |
| 6. Hardening | 16 to 19 | Security review, backups + restore drill, performance test, user guide | Restore drill done |
| 7. Pilot | 20+ | Parallel run with one department | Differences explained; mentor sign-off |

### 18.1a Is 20 weeks realistic? (review)
- Tight. The table overlaps phases. Your decisions remove most waiting; only the target-revision rule still needs the mentor, and it defaults to manual.
- To protect the core: build a **thin end-to-end slice by week 8** (one course: roster import, marks import, engine, course result page, one PDF) before widening any module.
- Use Django admin for setup screens (structure, courses, COs, users) in release 1; build custom pages only for lecturers (marks) and results.
- Keep 2 weeks of buffer before the pilot; if behind at week 12, move the method wizard, dry-run diff and Action Taken Report to "should".

### 18.2 Must / should / later
- **Must (release 1):** everything in phases 0 to 5 except the items below.
- **Should (if time):** guided method wizard (fallback: admin edits method in a validated form), dry-run diff, two-factor login, hash-chained audit verification job.
- **Later:** indirect surveys (forms, scales, response-rate rules), REST API, SSO, translations, mobile marks entry, credit-weighted roll-ups (configurable already, UI later).

### 18.3 Team roles (suggested)
- Engine + tests owner; marks + imports owner; setup + roster owner; results + reports owner. Everyone reviews someone else's work. One person also owns deployment/backups.

---

## 19. Requirements traceability (checked item by item)

### 19.1 Objectives
| Objective | Where in design |
|---|---|
| 1 Automate, no typed levels | 6.1, 6.2, 6.8 |
| 2 Configurable without code | 6.3, 6.4, 7 |
| 3 Reproduce reference exactly | 2.1, 16.1 golden tests |
| 4 Explainable | 6.5 |
| 5 Reproducible past results | 6.1, 6.9, 7.2, 12 |
| 6 Real rosters | 5.2, 11.1 |
| 7 Simple for lecturers | 8.4, 10.2 |
| 8 Many colleges safely | 13.1 |
| 9 Zero cost | 4, 14 |
| 10 ERP-independent, integration later | 15 |
| 11 Quality process | 8.9, 5.5 |

### 19.2 Functional requirements
| F | Requirement | Section |
|---|---|---|
| F1 | Structure, users, roles | 5.1, 9 |
| F2 | Course identity not tied to code | 5.1 `Course`/`CourseCode` |
| F3 | Open electives, twin courses | 5.1 `CourseGroup` |
| F4 | COs/POs/PSOs versioned, mapping | 5.3 |
| F5 | Assessments, questions, parts, choice, CO tags | 5.4, 8.3 |
| F6 | Lecturer entry/import for own sections | 8.4, 9, 11.1 |
| F7 | All mark states | 5.4 |
| F8 | Validation, import source kept | 11.1, 5.5 `ImportBatch` |
| F9 | Change history | 5.4 `MarkChange`, 12 |
| F10 | Lock and reopen | 8.7, 12 |
| F11 | Automatic calculation, nothing typed | 6 |
| F12 | Intermediate values, denominators | 6.5 |
| F13 | Recalculate, keep versions | 6.6, 5.5 `CalculationRun` |
| F14 | Provisional, flags | 6.7 |
| F15 | Section/course/department/batch, batch comparison | 6.2, 8.10 |
| F16 | Targets and revision | 6.3 `TargetRevise`, 8.11 |
| F17 | Observations, action plans, action taken | 8.9 |
| F18 | Gap view | 8.9, 10.1 |
| F19 | Approvals, frozen signed results | 8.7 |
| F20 | Overrides with reason | 6.8 |
| F21 | Reports with version and status | 11.3 |
| F22 | Import old Excel, side-by-side | 8.13 |
| F23 | Scoped access, separation, audit | 9, 13.1, 12 |

### 19.3 Business rules R1 to R27
All mapped to step types in 6.3 (R1/R2 `QuestionPass`; R3/R4 `Precision`; R5/R6 `Denominator`; R7 `AggregateToCO`; R8 `Bands`; R9 `MergeTools`; R10 6.8; R11/R12 `WeightedCombine`; R13 `Average`; R14 `TargetCompare`; R15 `TargetRevise`; R16 `RollUp`; R17 to R19 `MapToOutcomes`; R20/R21 batch `RollUp` + `WeightedCombine`; R22 `Target` per programme; R23 `CountStatus` + batch report; R24 mark states; R25 to R27 trace + warnings 6.5).

### 19.4 Configurability list (requirements section 8)
Pass mark ✔ `QuestionPass` · bands ✔ `Bands` · tools, weights, behaviours, CO coverage ✔ `tools` + `applies_to` · aggregation ✔ `AggregateToCO`, `MergeTools`, `RollUp` · choice rule ✔ `ChoiceSelect` · denominator ✔ `Denominator` · direct/indirect ✔ `WeightedCombine`, `IndirectInput` · CO-PO formula ✔ `MapToOutcomes` · roll-up weights ✔ `RollUp` · targets + revision ✔ `Target`, `TargetRevise` · truncation and compared value ✔ `Precision` · absent handling ✔ `NormaliseStates` · override roles ✔ 9 + method setting · scope of settings ✔ 7.1 · versioned and reused ✔ 7.2.

### 19.5 Non-functional requirements
Cost ✔ 4, 14 · usability ✔ 10 · correctness ✔ 2, 16 · reproducibility ✔ 6.1, 12 · explainability ✔ 6.5 · security/privacy ✔ 13 · scale ✔ 3.1, 16.1 performance · availability/recovery ✔ 14.4 · maintainability ✔ 3.3, 17 · portability ✔ 11.2, 15.

### 19.6 Open items (requirements section 18): how the design handles each
Every open item is a **setting with a default**, so none blocks building: 1 part-level storage (settled by evidence, 2.2.4) · 2 `Denominator` (decided: choice → attempted, compulsory → all who sat) · 3 `RollUp.stage` · 4 `TargetRevise` (decided: manual until the rule is known) · 5 `Precision.compare_with` (decided: unrounded; round or truncate per level) · 6 `RollUp.weights` · 7 batch membership rule (8.10, `BatchMembership`) · 8 `Denominator` per tool · 9 lab method config · 10 exam-branch role + `ScriptMapping` · 11 shared course definition + separate offerings · 12 programme-level PO targets · 13 `IndirectInput` placeholder · 14 report templates · 15 in release 1 · 16 anonymisation script · 17 second-method golden test · 18 engineering/NBA first · 19 `Bands` labels and count.

---

## 20. Critical review of this design

I reviewed the design against the requirements and against the evidence. What holds, what is weak, and what I changed while reviewing.

### 20.1 Changes made during review
- **Marks stored per part, not per question:** changed after the SEE sheet showed per-part CO tags and percentages (2.2.4).
- **Per-question pass-mark override added:** without it, the reference result cannot be reproduced (2.2.1).
- **Display precision separated from compared value, per level:** added after the batch file showed rounding and the PO9 flip (2.2.3).
- **Render PostgreSQL removed** from the demo plan (deleted after 30 days).
- **Marks grid changed from AG Grid Community to Jspreadsheet CE / Tabulator:** paste from Excel is an AG Grid Enterprise (paid) feature, and lecturers need paste.
- **Background job queue removed** from release 1 (not needed at this data size; one less service on free hosting).
- **RLS made mandatory, not optional:** isolation is an acceptance scenario and student data is involved; app-only filtering has a single point of failure.

### 20.2 Weak points and how they are handled
| Weak point | Why it matters | Mitigation |
|---|---|---|
| The step catalogue may not fit some college | "Any college" claim | Golden test with two published methods before UI work; `AggregateToCO` and `RollUp` already include common alternatives; new steps are a product release |
| Only one real method to learn from | Over-fitting | Same as above; keep Vasavi specifics as config, never in code |
| Typed pass marks and rounding choices change official results | Wrong "Attained" status | Decided (section 21); dry-run diff and near-target warnings |
| **The app's numbers differ from the college's own reports** (Deep Learning 2.18 vs 2.32 with strict 60%) | The college may distrust the app or reject the pilot | Before the pilot, show the IQAC and mentor the comparison table from the prototype (runs G to J) and let them choose: accept strict 60% or record the typed pass marks as approved overrides |
| HTMX is less familiar to students than React | Learning time | Small surface; most screens are Django forms; grid is one component |
| Free hosting sleeps/limits | Bad first impression in demo | Warm the demo before meetings; real use self-hosted |
| Self-hosting needs college IT | Adoption | One-command Docker install, backup script, admin guide |
| RLS adds complexity | Bugs in policies | One generic policy; isolation test on every endpoint |
| Data protection when we host | Legal exposure | Self-host by default for real data; anonymised demo |
| Scope growth (surveys, ERP) | Late core | Must/should/later list (18.2) |
| Students graduate and leave the project | Nobody maintains it; colleges stuck | Boring, popular stack; rules guide and admin guide; open-source licence and public repo so others can continue; hand-over plan to the college's IT or the next student batch |
| Under-18 students and DPDP | Consent duty may apply | Ask the college's legal/IQAC office before the pilot (13.3) |

### 20.3 What this design deliberately does not do
- No arbitrary formulas typed by users (requirements 5.2).
- No custom code per college.
- No live ERP connection in release 1.
- No mobile app; no paid service.

---

## 21. Decisions (made 2026-11-09) and what is still open

### 21.1 Decided
| # | Decision | What the design does |
|---|---|---|
| 1 | Internal-II pass marks: default | Strict 60% of max; optional per-part override with reason and IQAC approval (5.4, 6.3) |
| 2 | Rounding | Each level has a round-or-truncate setting; default truncate; compared value default unrounded (6.3 `Precision`) |
| 3 | Denominator | Set per question: choice question → students who attempted it; compulsory → everyone who sat (6.3 `Denominator`) |
| 4 | Target revision | Manual until the rule is known (6.3 `TargetRevise`) |
| 5 | Team and timeline | Python team of 3 to 5, about 20 weeks to a pilot (1.2, 18) |
| 6 | Hosting real data | The college self-hosts; demo on free cloud with anonymised data (14) |
| 7 | Stack | Django + PostgreSQL + HTMX (4) |
| 8 | Below 10% | Result stops for review (provisional) (6.3 `Bands`) |
| 9 | Tool with no value for a CO | Stops for review (6.3 `MissingData`) |
| 10 | Supplementary / improvement exams | Regular attempt only (5.4) |
| 11 | Project licence | MIT (1.2) |
| 12 | Under-18 students | Assumed exempt for the demo (anonymised data); confirm with the college before the pilot (13.3) |

### 21.2 Still open (none blocks building)
1. **Target revision rule** (+0.5 points, +0.5%, or ×1.1): ask the mentor; manual until then.
2. **Pilot numbers:** the college accepts strict 60% (2.18) or approves the typed pass marks as overrides (2.32). Needed before the pilot, not before building.
3. **Internal-II "any 4 of 6":** inferred from the marks (66 of 67 students answered exactly 4); confirm from the question paper.
4. **Under-18 consent:** confirm with the college's legal or IQAC office before the pilot.
5. **Free-tier terms:** re-check Render and Neon before the demo.

---

## 22. Review log (v1.1 and v1.2)

### v1.1
Two review passes on 2026-11-08. Pass 1 read the design against the requirements, the workbooks and itself. Pass 2 re-checked every fix and searched the file for stale text. Evidence: `prototype/synthetic-results.txt`.

### 22.1 Issues found and fixed
| # | Area | Issue in v1.0 | Fix in v1.1 | Section |
|---|---|---|---|---|
| 1 | Engine | Below-10% "flag" gave no number to the weighted sum, so the calculation was undefined | `Bands` now also says which value later steps use (default: stop for review) | 6.3, 21 |
| 2 | Engine | No rule when a tool has no value for a CO (no part tagged, or nobody attempted) | New `MissingData` step | 6.3, 21 |
| 3 | Engine | Config said SEE "missing counts as 0", but in the per-part method a missing answer has no part or CO | Clarified; recorded as a note only; test added | 6.3, 6.4, 16.2 |
| 4 | Engine | Completeness rule would mark every SEE run provisional (unchosen questions are always blank) | Completeness now uses the mark-sheet row status | 5.4, 6.7 |
| 5 | Engine | Merged internal levels can be 2.5; not stated | Stated; printed as 2.5 | 6.3 |
| 6 | Engine | Typed indirect value 3 could hide a weak direct result | Reports label it and show direct-only too | 6.3 |
| 7 | Engine | Batch could mix signed and unsigned course values | `BatchInput` step, default signed only | 6.3 |
| 8 | Engine | Old method configs could stop working after a schema change | Schema versions and tested converters | 6.9 |
| 9 | Precision | "Truncate everywhere" and "prefer higher values" conflict at PO9 | Stated as a conflict for you to decide (decided in v1.2) | 2.2.3, 21 |
| 10 | Precision | Float maths risk was a claim only | Proved: float gives 2.51 for the reference CO1, decimals give 2.52; test added | 2.1, 16.1 |
| 11 | Data model | An offering belonged to one programme, so a common CSE/CSE-AIML course could not be split per programme | Programme and batch moved to the section; results per programme | 5.1, 8.10 |
| 12 | Data model | No way to tell "not entered yet" from "left blank" | `MarkSheetRow` with status | 5.4 |
| 13 | Data model | Two people editing the same cell could overwrite each other | Row version (optimistic locking) | 5.4 |
| 14 | Data model | Supplementary / improvement exams not handled | `attempt` field; method setting; decision 10 | 5.4, 21 |
| 15 | Data model | Earlier batches (2019-23, 2020-24) had nowhere to live, so the three-batch comparison could not work | `HistoricResult` import | 5.5, 8.13 |
| 16 | Data model | PEOs (F4) missing; credits missing for a later weighted roll-up | Added | 5.1, 5.3 |
| 17 | Data model | Proof uploads could fill Neon's 1 GB free storage | `StoredFile` with caps and switchable storage | 5.5, 14.2 |
| 18 | Security | RLS described but not how to set it safely; a reused connection could leak one college's setting to another request | `SET LOCAL` in every transaction, fail-closed policy, non-owner role, rules for commands | 13.1 |
| 19 | Privacy | DPDP timing, log retention, processor duties, under-18 students not covered | Added with dates; under-18 question raised | 13.3, 21 |
| 20 | Operations | Backups relied on GitHub Actions, which cannot reach a server inside a college network | Local backup container + off-site copy for self-hosting | 14.4 |
| 21 | Operations | No update procedure for self-hosted colleges; no HTTPS plan for campus-only servers | `update.sh`, supported versions, internal certificates | 14.3 |
| 22 | Testing | Golden fixtures would contain real roll numbers in a possibly public repository | Fixtures anonymised | 16.1 |
| 23 | Testing | Batch golden test was presented as end-to-end; it only checks the roll-up | Stated | 16.1 |
| 24 | Workflow | "Signed" could be read as a legal digital signature | Defined as approval records; wet signatures on PDF | 8.7 |
| 25 | Workflow | No reminders for marks due or approvals | Task list; email as "should" | 8.12 |
| 26 | Roles | "Principal" in the table vs "director" in the workflow | Same role, stated | 9 |
| 27 | Plan | 20 weeks for the full scope was optimistic, with no slice or buffer | End-to-end slice by week 8, Django admin for setup, buffer, cut list | 18.1a |
| 28 | Risk | Project dies when the students graduate | Hand-over and open-source plan | 20.2 |
| 29 | Text | Summary said "4 issues" but section 2 lists 5 | Fixed | 1.1 |
| 30 | Text | Config used an invalid value (`"undecided"`) for target revision | `"manual"` | 6.4 |
| 31 | Data model (pass 2) | The new blank-cell rule contradicted Internal-I's class-strength denominator | Blank meaning now follows the tool's denominator setting | 5.4 |

### 22.2 Checked and found sound (no change)
- Architecture (modular monolith, pure engine) still fits: data stays small, the team is small, and free hosting allows one service.
- Every functional requirement F1 to F23, rule R1 to R27, configurability item and acceptance scenario 1 to 20 still maps to a section (section 19; references updated).
- Engine results in section 2 re-run unchanged on 2026-11-08.
- Tech stack licences: all MIT, BSD, Apache, MPL or PostgreSQL licences; no paid feature is needed (the AG Grid paste issue was fixed in v1.0).

### 22.3 Known limits that remain (not fixable by design alone)
- Only one real method has been seen; the "any college" claim depends on testing two published methods (16.1).
- Free-tier terms change; checked on 2026-11-06 and must be re-checked before the demo.
- Five rules change official results and need you or the mentor (section 21, items 1, 2, 8, 9, 10). *(Decided on 2026-11-09; see v1.2.)*

### v1.2
Your decisions applied, then two strict review passes on 2026-11-09: pass 1 read every section against the requirements, the workbooks and itself; pass 2 re-checked each fix, re-ran the prototype and searched the file for stale text. New prototype runs G to J and tests T9 are in `prototype/`.

| # | Area | Issue in v1.1 | Fix in v1.2 | Section |
|---|---|---|---|---|
| 1 | Decisions | 12 decisions were open | Applied everywhere; section 21 now records them | 21 and as listed there |
| 2 | Evidence | Effect of the decided rules on the reference was unknown | Ran them: Deep Learning 2.18 Not attained by default; 2.32 with overrides | 1.1, 2.2 |
| 3 | Evidence | Decided SEE rule untested | Matches the workbook's SEE percentages for 4 of 5 COs to 2 decimals; levels all match | 2.2.2 |
| 4 | Engine | Internal-II treated as compulsory parts; it is "any 4 of 6" | Choice group best 4; one student's 5th answer dropped; levels unchanged | 2.2.2, 6.4 |
| 5 | Engine | Denominator options could not express "choice → attempted, compulsory → all" | `by_choice` mode, choice = member of a choice group | 6.3, 5.4 |
| 6 | Engine | Students absent for a whole assessment had no rule | `whole_assessment_absent` (default exclude) | 6.3 |
| 7 | Precision | One global precision setting; you asked for round or truncate | Per-level mode and places | 6.3, 6.4 |
| 8 | Precision | Python's default decimal rounding (half-even) differs from Excel ROUND | Mode always explicit; test T9 | 6.3, 16.1 |
| 9 | Precision | A % could display as 60.00 yet get Level 2 | Bands use unrounded %; band-edge marker on reports | 6.3 |
| 10 | Engine | "All mappings are 0" had no defined PO result | `all_zero`: blank (default) or 0; batch skips blanks, counts zeros | 6.3 |
| 11 | Engine | Every autosave would store a new calculation run | One latest run per scope; permanent runs at submit, approve, sign, snapshot | 6.6 |
| 12 | Engine | Overrides after approval could change a signed result | Overrides only before approval; afterwards via reopen | 6.8 |
| 13 | Engine | No owner or screen for entering the indirect value | IQAC enters it with a source note; provisional until entered | 6.3, 8.10a |
| 14 | Data model | Student had one batch; detained students change batch | `BatchMembership` with history | 5.2 |
| 15 | Data model | Enrolment section vs home section was ambiguous | Enrolment section decides where marks count | 5.2 |
| 16 | Data model | Pass-mark overrides had no approver | Coordinator enters, IQAC approves | 5.4 |
| 17 | Workflow | No "return for correction" before approval | Coordinator can return a section with a reason | 8.7 |
| 18 | Workflow | Section, course and batch approval levels were mixed in one line | Three separate state flows | 8.7 |
| 19 | Workflow | Batch report had no sign-off or freeze | IQAC → HOD → principal; frozen with the course runs it used | 8.7 |
| 20 | Workflow | Two people or an import could overwrite the same marks | Refused save message; short import lock | 8.4 |
| 21 | Import | Header-based column guessing would fail on Internal-II (unlabelled parts) | Columns from the question paper/template | 11.1 |
| 22 | Import | The mentor's batch workbook crashes openpyxl (chart XML) | Strip charts/drawings from a copy and retry | 11.1 |
| 23 | Import | Formula cells without cached values; XML attack risk | Reject with a clear message; `defusedxml` | 11.1 |
| 24 | Security | Upload limit 10 MB in one place, 5 MB in another | Imports 10 MB, stored proofs 5 MB | 13.2 |
| 25 | Security | No reset path where a college has no email | Admin-issued one-time link | 13.2 |
| 26 | Audit | Hash chain could fork under concurrent writes | Advisory lock per college | 12 |
| 27 | Audit | Deleting a student would break the hash chain | Audit uses internal ids only | 12 |
| 28 | Backups | Backup encryption key ownership undefined | Key holder, sealed copy, checked in the drill | 14.4 |
| 29 | Operations | Secrets handling for CI backups not stated | GitHub secrets | 14.3 |
| 30 | Operations | PDF memory on the 512 MB free demo | SVG charts; test largest report | 14.3 |
| 31 | Testing | Golden test 1 would fail under the decided default | Two golden tests: with overrides (2.32) and without (2.18) | 16.2 |
| 32 | Plan | Scenario 16 needs two published methods but nobody owned finding them | Added to phase 1 | 18.1 |
| 33 | Plan | College report layouts not planned | Phase 5 copies the mentor's report layouts | 18.1 |
| 34 | Plan | Plan assumed waiting for mentor answers | Updated: only target rule remains, default manual | 18.1a |
| 35 | Risk | App numbers will differ from the college's reports | Comparison shown to IQAC and mentor before the pilot | 20.2 |
| 36 | Text | Summary and diagram said all backups run on GitHub Actions | Demo vs self-hosted stated | 1.1, 3.2 |
| 37 | Text | Summary claimed an exact match without the override condition | Qualified | 1.1 |
| 38 | Text | Assumptions table still said all questions unanswered | Marks which are confirmed | 1.2 |
| 39 | Text | Config example used old denominator values and a removed zero-strength key | Updated | 6.4 |
| 40 | Text | Lab config did not say final = direct | Stated | 6.4 |
| 41 | Text | Open items list did not show decisions | Updated | 19.6 |
| 42 | Engine (pass 2) | "Stop for review" had no way to be released | Released by an override with a reason | 6.8 |
| 43 | Roles (pass 2) | Roles table lacked accept/return and batch preparation | Added | 9 |

**Checked and sound in v1.2:** architecture; stack; isolation rules; every F1 to F23, R1 to R27 and scenario 1 to 20 still maps (section 19); prototype runs D (exact match) and the batch roll-up re-run unchanged on 2026-11-09.

---

## Sources (checked 2026-11-06)
- Free-tier facts: see `solution-options.md` sources (Neon, Render, Cloudflare, Supabase, Oracle).
- AG Grid Community vs Enterprise (clipboard is Enterprise): https://www.ag-grid.com/javascript-data-grid/community-vs-enterprise.md
- Jspreadsheet CE vs Pro (CE is MIT; copy/paste from Excel in CE; vendor's own page): https://bossanova.uk/jspreadsheet/blog/jspreadsheet-ce-vs-pro
- Evidence for section 2: `prototype/course-results.txt`, `prototype/batch-results.txt`, `prototype/synthetic-results.txt`.
- DPDP Rules 2025 (notified 14 Nov 2025; phased rollout): https://www.scconline.com/blog/post/2025/12/26/digital-personal-data-protection-rules-2025-key-highlights/ and https://www.amsshardul.com/insight/enforcement-of-the-dpdp-act-and-notification-of-the-dpdp-rules/ (secondary sources; check the Gazette text before relying on them)
