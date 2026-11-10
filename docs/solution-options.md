# Solution options and trade-offs (design phase, step 1)

**Version 1.0** · 2026-11-06 · Research only. **No decision is made here.** The recommendation at the end is **tentative**.
**Input:** `project-statement-final.md` v2.0 (requirements). Numbers like R11, F6 refer to it.

How to read the ratings:
- **Fit** = how well it meets our requirements (High / Medium / Low).
- **Learning** = effort for a student team (Low = easy).
- **Scale** = how far it goes as colleges are added.
- Free-tier numbers were checked on 2026-11-06. Some come from third-party pages (marked *unverified*). **Re-check each vendor's own pricing page before choosing.**

---

## 0. What drives the choice (from the requirements)
- **The hard part is the calculation and configuration, not the web pages.** Rules vary in numbers *and* in structure (section 8). Most of the risk sits in the engine.
- **Data is tiny.** One section is ~67 students; a whole college is a few MB per year. Scale problem = variety of methods, not volume. Any normal database is enough.
- **Correctness and traceability matter more than speed** (Objectives 3 to 5, F12, F13, F19).
  - Results must match the mentor's workbook exactly.
  - Truncation to 2 decimals (R3, R4) means **decimal arithmetic, not floating point**. With floats, 2.2 can be stored as 2.19999… and truncate to 2.19. This rules nothing out, but every option must use a decimal type.
- **Many colleges, separate data** (F23, scenario 19).
- **Zero budget.** Free tiers sleep, pause, expire or get cut. Official marks need backups (section 13).
- **Small student team, limited time.** Fewer moving parts wins.
- **Excel in, Excel/PDF out** (F6, F21, F22).
- **ERP integration later**, so keep clean import/export boundaries now.

---

## 1. Overall architecture options

### 1.1 Simple monolith (one app, one database)
- One codebase serves pages, API, calculations, reports.
- **Pros:** fastest to build; one deploy; easy to debug; fits free tiers (one service).
- **Cons:** can become tangled if modules are not kept apart.
- **Fit:** High. **Learning:** Low. **Scale:** Medium to High (data is small).

### 1.2 Modular monolith (one app, strict internal modules)
- Same as 1.1, but split into modules with clear boundaries: `setup`, `marks`, `engine`, `reports`, `quality`, `audit`, `integration`.
- The **engine is a pure library**: input = marks + config, output = results + explanation. No database or web code inside.
- **Pros:** all pros of 1.1; engine testable alone against the workbook; can be split out later if ever needed.
- **Cons:** needs discipline (code review, folder rules).
- **Fit:** High. **Learning:** Low to Medium. **Scale:** High.

### 1.3 Split services / microservices
- Separate services, e.g. auth, marks, calculation, reports, each with its own deploy.
- **Pros:** independent scaling and deploys; team members can own services.
- **Cons:** many deploys on free tiers (each sleeps separately, more cold starts); network calls between services; harder debugging, transactions and audit; big overhead for a student team; no volume problem to solve.
- **Fit:** Low. **Learning:** High. **Scale:** High (not needed).

### 1.4 Frontend SPA + backend API (two deployables)
- A React/Vue app talks to a JSON API.
- **Pros:** rich spreadsheet-like marks entry; API ready for later ERP integration; static frontend hosts free almost anywhere.
- **Cons:** two codebases, two languages possibly; auth across domains (CORS, tokens); more to learn.
- **Fit:** High. **Learning:** Medium. **Scale:** High.

### 1.5 Server-rendered app (+ HTMX or a little JS)
- Pages built on the server; small interactive parts (marks grid) added with HTMX or one JS component.
- **Pros:** one codebase; simplest auth (sessions); fast to build forms and admin screens.
- **Cons:** a fully Excel-like grid needs a JS grid component anyway; API for ERP must be added separately.
- **Fit:** High. **Learning:** Low. **Scale:** High.

### 1.6 Serverless functions (Cloudflare Workers, Vercel/Netlify functions)
- Each endpoint is a function; the provider runs it on demand.
- **Pros:** generous free request counts; no server to manage; no sleep delay on Cloudflare.
- **Cons:** strict CPU/time limits (Cloudflare Free: 10 ms CPU per request, 100,000 requests/day); heavy jobs (Excel import, PDF) may not fit; vendor-specific code; harder local testing.
- **Fit:** Medium. **Learning:** Medium. **Scale:** High.

### 1.7 Backend-as-a-Service (Supabase, Firebase, Appwrite, PocketBase)
- Ready-made database, auth, storage and API; we write mainly the frontend plus some functions.
- **Pros:** auth and CRUD for free; Supabase gives Postgres with row-level security (good for tenancy).
- **Cons:** business logic (the engine) still needs a home (edge functions, database functions or the browser); vendor lock-in; Supabase free pauses after 1 week idle *(unverified third-party)*; logic spread over places is harder to test and audit.
- **Fit:** Medium. **Learning:** Medium. **Scale:** Medium to High.

### 1.8 Low-code / no-code builders (Appsmith, Budibase, NocoDB, Baserow, Google Sheets + Apps Script)
- **Pros:** very fast admin screens and tables; open-source self-hostable versions exist.
- **Cons:** the configurable engine (choice rules, denominators, roll-ups, versioning, explainability) does not fit their models; hard to test; Sheets + Apps Script repeats the Excel problems we are trying to fix; multi-college separation weak.
- **Fit:** Low (OK for a throwaway prototype of screens). **Learning:** Low. **Scale:** Low.

### 1.9 Self-hosted per college (each college runs its own copy)
- Same app packaged with Docker; a college runs it on its own server or PC.
- **Pros:** truly zero cost for us; the college owns its student data (simpler under India's DPDP Rules 2025); no free-tier limits; isolation by design.
- **Cons:** colleges need someone to install, update and back it up; harder to push fixes; support burden.
- **Fit:** High as a deployment *option*. **Learning:** Medium (Docker). **Scale:** High (each college scales itself).

### 1.10 Local-first / desktop / offline (Electron, Tauri, PWA with local database)
- **Pros:** works without internet; no hosting.
- **Cons:** data on one machine; sharing between lecturers, HOD and IQAC is hard; sync is a hard problem; approvals and audit weak.
- **Fit:** Low. **Learning:** High. **Scale:** Low.

### 1.11 Configuration approach (cross-cutting)
- **Config as code:** each college's method written as code (a plugin or a script).
  - Pros: unlimited flexibility. Cons: breaks "no code changes" (Objective 2); every college needs a developer; risk of one college's code affecting another.
- **Config as data:** method stored as versioned records (JSON or tables) that the engine reads.
  - Pros: meets Objective 2; versions per period (scenario 14); shown in reports; safe across colleges. Cons: engine must be designed carefully; some rare methods may need a new building block (a product change, not a college change).
- **Hybrid:** config as data, plus a small safe formula language for weighted combinations. See section 4.

---

## 2. Frontend options

| Option | Pros | Cons | Fit | Learning | Scale |
|---|---|---|---|---|---|
| **Server templates + HTMX** (Django/Laravel/Rails templates) | One codebase; simple; no build step; good for forms | Rich grid needs a JS component; less "app-like" | High | Low | High |
| **React (Vite) SPA** | Biggest ecosystem; most grid/table libraries; many tutorials | State, routing, build tooling to learn; separate API needed | High | Medium | High |
| **Next.js (React full stack)** | Frontend and backend in one TypeScript project | Framework changes often; server/client split confuses beginners; Vercel Hobby is for non-commercial use only | High | Medium-High | High |
| **Vue / Nuxt** | Gentler than React; good docs | Smaller ecosystem than React | High | Low-Medium | High |
| **Angular** | Strong structure; common in Indian industry | Heavy; steep learning | Medium | High | High |
| **Svelte / SvelteKit** | Small, fast, easy syntax | Smaller ecosystem; fewer grid options | Medium | Low-Medium | High |

**Marks-entry grid** (the screen lecturers use most; must feel like Excel: paste, keyboard, row errors):
- **AG Grid Community** (MIT, free): keyboard, validation, large tables. **Clipboard paste**, range fill and Excel export are Enterprise-only (paid). *[Corrected 2026-11-06 in solution-design.md review.]*
- **Jspreadsheet CE / Tabulator** (MIT): paste from Excel, keyboard, validation.
- **TanStack Table** (MIT): headless, flexible, but we build the editing UI ourselves.
- **Handsontable:** most Excel-like, but free only under a non-commercial licence. Risk if the product is ever used commercially.
- **Plain HTML table with inputs:** zero dependency, enough for 67 rows; paste support must be written.
- **Charts:** Chart.js or Apache ECharts (both free, MIT/Apache).

---

## 3. Backend options

| Option | Language | Pros | Cons | Fit | Learning | Scale |
|---|---|---|---|---|---|---|
| **Django** | Python | Built-in admin (free setup screens), auth, ORM, migrations; `Decimal` built in; best Excel/data libraries (openpyxl, pandas); history plugin for audit | Templates feel dated without HTMX; async weaker | High | Low-Medium | High |
| **FastAPI** | Python | Modern, fast, auto API docs (OpenAPI) | No admin, auth or ORM built in (assemble yourself) | Medium-High | Medium | High |
| **Flask** | Python | Tiny, easy start | Everything added by hand; structure drifts | Medium | Low | Medium |
| **Node + Express / NestJS** | TypeScript | Same language as frontend; NestJS gives structure | No built-in decimal (need a library like decimal.js); more packages to pick | High | Medium | High |
| **Next.js server actions / routes** | TypeScript | One project with frontend | Mixing UI and logic; vendor-shaped | Medium-High | Medium-High | High |
| **Spring Boot** | Java | Very robust; `BigDecimal`; taught in many Indian colleges | Verbose; heavier memory (bad on 512 MB free hosts) | Medium-High | High | High |
| **Laravel** | PHP | Fast CRUD; cheap PHP hosting exists | PHP less taught now; free PHP hosts are unreliable | Medium | Medium | High |
| **ASP.NET Core** | C# | Strong typing, `decimal`, good performance | Fewer free hosting options | Medium | Medium-High | High |
| **Rails** | Ruby | Very fast CRUD | Ruby rarely known by student teams | Medium | Medium-High | High |

---

## 4. Calculation / rules engine (the core)

What it must do (sections 7 and 8): per-question pass checks, choice rules (best N of M, best K parts), denominators (attempted / enrolled / SEE-attempted), bands to levels, averaging across internals, weighted direct CO, direct/indirect split, course average, CO-PO weighted mapping, section/department/batch roll-ups, truncation settings, flags, explanations, versions.

### 4.1 Hard-coded formulas + numeric settings
- Formulas written in code; only numbers (60%, weights, bands) are settings.
- **Pros:** simplest; fastest to match the workbook.
- **Cons:** structure differences (new tool behaviour, other choice rules, other roll-up) need code changes. Fails scenario 16 and Objective 2.
- **Fit:** Low (OK as the very first milestone). **Learning:** Low.

### 4.2 Config as data: a catalogue of building blocks (pipeline)
- The product ships a fixed set of **step types**, each with parameters. A college's method = a saved, versioned list of steps. Example:
  - `QuestionPass(threshold=60%, boundary=">=")`
  - `ChoiceSelect(best_n=5, from=[Q11..Q17], parts_rule="best 2 of Q17", missing=0)`
  - `Denominator(mode="attempted")`
  - `PerStudentAverage(tools=[Quiz1..3], absent=0)`
  - `Bands([60,50,10], below="flag")`
  - `Combine(weights={Internal:0.30, Assignment:0.05, Quiz:0.05, SEE:0.60})`
  - `RollUp(level="section→course", method="average", stage="CO attainment")`
  - `Round(mode="truncate", decimals=2, applies_to="final")`
- Every step records its inputs, outputs and counts, so every number is explainable (F12).
- **Pros:** meets "no code changes" for all variations in section 8; validated by forms (no syntax errors); easy to show in reports; easy to version; testable step by step.
- **Cons:** we must design the catalogue well; a truly new method needs a new step type (a product release).
- **Fit:** High. **Learning:** Medium.

### 4.3 Safe expression language (formulas typed by an admin)
- Admin types formulas, e.g. `0.3*INT + 0.05*ASG + 0.05*QZ + 0.6*SEE`, evaluated in a sandbox.
- Libraries: Python **simpleeval** or **asteval**; JS **expr-eval** or **filtrex**; Google **CEL** (cel-python, cel-js); **JSON Logic** (rules stored as JSON, many languages).
- Excel-style formula engines: **formulajs** (MIT, Excel functions in JS); **HyperFormula** (GPLv3 or paid licence: licence risk); Python **formulas** / **pycel** (evaluate Excel files).
- **Pros:** flexible for weights and combinations; familiar to Excel users.
- **Cons:** "unrestricted formulas" are out of scope (5.2); typos produce wrong official results; harder to explain; must guard against abuse (loops, huge numbers). Not good for set-wise logic (best 5 of 7, denominators).
- **Fit:** Medium (good *inside* 4.2 for combination steps only). **Learning:** Medium.

### 4.4 Business rules engine (Drools, json-rules-engine, Easy Rules, GoRules Zen / DMN decision tables)
- **Pros:** made for "if condition then outcome" decisions; decision tables suit level bands.
- **Cons:** poor at aggregation over sets of students and questions (our main work); Drools is Java and heavy; extra concept to learn.
- **Fit:** Low-Medium (bands only). **Learning:** High.

### 4.5 Spreadsheet as the engine (college uploads its Excel template; we fill marks and evaluate)
- **Pros:** zero change for colleges; matches their current habits.
- **Cons:** brings back every Excel problem in section 2 of the requirements (typed counts, `>` vs `>=`, hard-coded `/67`); weak explanations and validation; formula engines do not support every Excel function.
- **Fit:** Low (useful only as a *comparison tool* for F22). **Learning:** Medium.

### 4.6 Calculation in SQL (views / stored procedures)
- **Pros:** fast; close to the data; fewer moving parts.
- **Cons:** configurable structure in SQL becomes very hard; hard to test and explain; ties logic to one database.
- **Fit:** Low-Medium. **Learning:** Medium-High.

### 4.7 Dataframe engine (pandas / Polars) inside 4.2
- Steps implemented with dataframes: group, filter, average.
- **Pros:** concise code for "% of students ≥ 60% per question per CO"; easy to export intermediate tables to Excel.
- **Cons:** float by default (must force decimal or rational handling at the boundary and truncation points); extra library.
- **Fit:** Medium-High (an implementation detail of 4.2). **Learning:** Medium.

### 4.8 When to calculate
- **On demand (recalculate each time):** data is tiny (milliseconds). Simplest; always fresh. **Recommended baseline.**
- **Cached results, recalculated on change:** faster dashboards for batch roll-ups over 8 semesters; needs invalidation rules.
- **Background jobs (queue, e.g. Celery, RQ, BullMQ):** only if imports or PDF generation get slow; needs Redis (another free service).
- **Frozen snapshots at sign-off (required by F19, scenario 20):** store the full result and the config version used, whichever option is picked.

### 4.9 Testing the engine (applies to all)
- **Golden tests:** mentor workbook (Appendix A, B) as fixed expected outputs.
- **Edge-case tests:** boundaries, truncation, blanks, absent, best-5, below 10% (section 16).
- **Property tests:** Hypothesis (Python) or fast-check (JS) to try random marks.
- **Decimal types:** Python `Decimal`, Java `BigDecimal`, C# `decimal`, JS `decimal.js` or `big.js`.

---

## 5. Database options

| Option | Pros | Cons | Fit | Learning | Scale |
|---|---|---|---|---|---|
| **PostgreSQL** | Relational (our data is very relational); exact `numeric` type; JSONB for configs; row-level security for tenancy; many free hosts | Needs a server (or a hosted free tier) | High | Medium | High |
| **MySQL / MariaDB** | Well known; exact `DECIMAL`; JSON column | No row-level security; JSON weaker | High | Low-Medium | High |
| **SQLite** (or Turso / libSQL, Cloudflare D1) | Zero setup; one file; easy backups; great for self-hosted per college | One writer at a time (fine at our size); hosted versions have daily limits (D1 Free queries fail past daily row limits since 2026-09-01) | Medium-High | Low | Medium |
| **MongoDB (Atlas free 512 MB)** | Flexible documents for configs | Our data (students, enrolments, marks, mappings) is relational; joins and integrity are harder; Decimal128 needed | Low-Medium | Medium | High |
| **Firebase Firestore** | Real-time, free Spark plan | NoSQL; aggregation queries limited; vendor lock-in | Low | Medium | High |

**Data-model choices inside the database:**
- **Marks storage:** one row per student × question part (normalised; easiest to validate and audit) vs one JSON blob per student per assessment (simpler, harder to query). Requirements (R24 mark states, F9 history) favour **one row per mark cell**.
- **Config storage:** JSON document per methodology version (easy versioning) vs many tables (easier validation). Common pattern: JSON validated by a schema (JSON Schema / Pydantic / Zod).
- **Identity:** internal student id separate from roll number (section 9); external-id mapping table for later ERP links.

---

## 6. Authentication and roles

| Option | Pros | Cons | Fit | Learning |
|---|---|---|---|---|
| **Framework built-in auth** (Django auth, Laravel Breeze, Spring Security) | Free, inside our database, no vendor | We handle password reset email | High | Low |
| **Google sign-in (OAuth)** | No passwords to store; many colleges use Google Workspace | Not every college or staff has Google accounts | High (as an extra) | Low-Medium |
| **Auth.js / Lucia-style libraries** (JS) | Free, self-contained | Setup effort; library churn | Medium-High | Medium |
| **Supabase Auth** | Free tier includes 50,000 monthly users *(unverified)*; works with Postgres RLS | Ties us to Supabase | Medium-High | Medium |
| **Keycloak** (self-hosted, open source) | Full SSO, SAML, LDAP; good for later ERP/college SSO | Heavy (Java, ~1 GB RAM); overkill now | Low now, Medium later | High |
| **Clerk / Auth0 free tiers** | Polished | Vendor limits, paid upgrade path, data abroad | Low-Medium | Low |

**Role model (needed whichever option):**
- **Scoped roles:** role + scope, e.g. "Lecturer of Course X, Section B, 2025-26"; "HOD of CSE"; "IQAC of College Y".
- **Options:** simple RBAC table (enough) vs policy libraries (django-guardian, CASL, Casbin, Oso) vs database row-level security.
- **Email for resets/notifications:** free options exist (e.g. Brevo, Resend free tiers *(unverified limits)*), or Gmail SMTP for demos. Note: Render free blocks outbound SMTP ports.

---

## 7. Excel / CSV import and export

| Option | Pros | Cons |
|---|---|---|
| **Python openpyxl** (+ pandas) | Read/write .xlsx with styles; can fill a college's own template | Server memory for big files (ours are small) |
| **JS SheetJS (Community)** | Parse in the browser, so the server gets clean JSON and preview is instant | Community edition distributed from their own site, not npm latest; styling needs Pro (paid) |
| **JS ExcelJS** (MIT) | Read/write with styles, Node or browser | Larger bundle |
| **Java Apache POI** | Very complete | Verbose, memory-heavy |
| **CSV only** | Simplest, universal | Lecturers live in Excel; loses multi-sheet and formatting |

**Import flow options (F6, F8, scenario 18):**
- **Upload → validate → preview with row errors → confirm** (recommended pattern regardless of library). Nothing saved until confirmed; source file kept.
- **Download a pre-filled template** (roster + question columns) → lecturer fills → upload. Removes most matching errors.
- **Paste from Excel into the grid.**
- **Matching rules:** roll number + section → internal student id; SEE script number → student through exam-branch mapping.

---

## 8. Multi-college tenancy

| Option | Pros | Cons | Fit | Learning | Scale |
|---|---|---|---|---|---|
| **Shared tables + `college_id` column** (filtered in code) | Simplest; one database; one migration | One missed filter leaks data | High | Low | High |
| **Shared tables + Postgres row-level security** | Database enforces separation even if code forgets | Postgres only; policies to learn and test | High | Medium | High |
| **Schema per college** (e.g. django-tenants) | Strong separation; per-college backup | Migrations run N times; more complex | Medium | Medium-High | Medium |
| **Database per college** | Strongest separation; easy delete/export | Free tiers limit project counts; ops heavy | Medium | High | Medium |
| **Instance per college** (self-hosted, 1.9) | Full separation; college owns data | Updates and support per college | High (as deployment option) | Medium | High |

- **Configuration inheritance** (university → college → department → course, section 8 "scope of settings") is separate from tenancy and needed in every option.

---

## 9. Hosting (free only)

Checked 2026-11-06. **Free tiers change often; Oracle reportedly halved its free ARM offer in 2026, and Cloudflare started enforcing D1 limits on 2026-09-01.**

### 9.1 App hosting
| Option | Free limits / behaviour | Risks | Fit |
|---|---|---|---|
| **Render** (web service) | 750 instance-hours/month; sleeps after 15 min idle; ~1 min wake-up; ephemeral disk | Slow first load; may restart anytime; outbound SMTP blocked | Medium-High (demo) |
| **Render** (Postgres) | 1 GB; **expires 30 days after creation, deleted after a 14-day grace**; no backups | **Not for real data** | Low |
| **Koyeb / similar PaaS** | Small free instance *(limits unverified)* | Terms change | Medium |
| **Fly.io, Railway, Heroku** | No ongoing free plan for new users (trial or paid) | Not free | Low |
| **Vercel Hobby / Netlify free** | Good for frontend + serverless functions | Vercel Hobby is non-commercial only; function time limits | Medium (frontend) |
| **Cloudflare Pages + Workers** | Workers Free: 100,000 requests/day, 10 ms CPU per request; no sleep | CPU limit too low for Excel/PDF work; vendor-specific | Medium |
| **GitHub Pages** | Static only, free | No backend | Frontend only |
| **PythonAnywhere free** | Always-on small Python app | Limited CPU; outbound internet restricted to a whitelist; must renew every few months *(unverified)* | Medium (demo) |
| **Oracle Cloud Always Free VM** | Full Linux VM (ARM, reportedly cut to ~2 vCPU / 12 GB in 2026 *(unverified)*) | Needs a card at sign-up; idle-reclaim reports; we manage the server | Medium-High |
| **Google Cloud Run / AWS / Azure free tiers** | Generous request quotas | Need a credit card; easy to incur charges by mistake | Medium (risk) |
| **College's own server** (Docker) | Free to us; data stays in the college | Needs college IT help | High (real use) |

### 9.2 Database hosting
| Option | Free limits | Risks | Fit |
|---|---|---|---|
| **Neon Postgres** (official page, updated 2026-10-01) | 1 GB per project, 20 GB total, 100 projects; 100 compute-hours/project/month; scales to zero after 5 min (sub-second wake); 6 h restore history | Compute suspended if hours run out (unlikely at our size); short restore window, so we need our own backups | High |
| **Supabase** | 500 MB DB, 1 GB files, 2 projects; **paused after 1 week idle** *(third-party source)* | Semester breaks cause pauses; must unpause manually | Medium-High |
| **Aiven free Postgres/MySQL** | Small free plan *(limits unverified)* | Terms change | Medium |
| **MongoDB Atlas M0** | 512 MB | NoSQL fit is poor | Low |
| **Turso / Cloudflare D1** (SQLite) | Daily row read/write caps | Queries fail past caps until midnight UTC | Medium |
| **Self-hosted Postgres/SQLite** on the same VM or college server | Unlimited within the machine | We do backups | High |

### 9.3 Backups (needed for official marks)
- **Scheduled `pg_dump`** via GitHub Actions (free minutes) or cron on a VM, stored encrypted (e.g. in a private repo, Google Drive, or Cloudflare R2 free 10 GB *(unverified)*).
- **Export everything per college** as Excel/JSON (also useful for portability and DPDP data requests).
- **Restore test** each term (section 13 says backups must be tested).

### 9.4 Data location and privacy
- DPDP Rules 2025: prefer an India region where offered (check Supabase/Neon region lists; Neon may only offer nearby Asian regions).
- Use anonymised data on any free cloud tier during development (open item 16).
- Real use by a college is safest **self-hosted** or on an account the college owns.

---

## 10. Reports, PDF and charts

| Option | Pros | Cons | Fit |
|---|---|---|---|
| **Browser "Print to PDF" with print CSS** | Zero server cost; WYSIWYG; signature blocks easy | Layout varies slightly by browser; user clicks Print | High |
| **Server HTML→PDF with headless Chromium** (Playwright/Puppeteer) | Pixel-exact | 300+ MB RAM: too heavy for free 512 MB hosts | Medium |
| **WeasyPrint** (Python, HTML/CSS → PDF) | Good print CSS; lighter than Chromium | Some CSS gaps; system libraries needed | High |
| **ReportLab / pdfmake / react-pdf** | Programmatic, exact layout | Every report coded by hand | Medium |
| **Excel export via a template** (openpyxl / ExcelJS) | Matches colleges' current formats; editable | Not tamper-evident | High (needed anyway, F21) |
| **Word/ODT template → PDF via LibreOffice headless** (docxtpl) | College edits the template itself | LibreOffice is heavy | Medium |
| **Embedded BI (Metabase, Apache Superset)** | Free dashboards | Another service; not needed for fixed NBA reports | Low |

- **Charts:** Chart.js or ECharts in the browser; static chart images for PDFs.
- **Every report must print:** college, batch, course, config version, data status (provisional/final), signatures (F21).

---

## 11. Audit trail, versioning and locking

| Option | Pros | Cons | Fit |
|---|---|---|---|
| **App-level change log** (who, when, old, new, reason) written by the app | Simple; can require a reason (R10, F20) | Can be bypassed by direct DB edits | High |
| **History tables via library** (django-simple-history, Hibernate Envers, PaperTrail, Prisma extensions) | Automatic per-row history | Storage grows (small for us) | High |
| **Database triggers / pgaudit** | Catches everything, even direct edits | Postgres-specific; harder to show "reason" | Medium |
| **Event sourcing** (store every change as an event, rebuild state) | Perfect history and replay | Complex; overkill | Low |
| **Immutable snapshots at sign-off** (result + config version + input hash) | Meets freeze (F19, scenario 20); reproducible | Must be designed in from day one | Required |
| **Tamper evidence** (hash chain over audit rows, or hash printed on signed PDF) | Shows nobody altered signed records | Extra work | Optional |

- **Config versioning:** each methodology version is immutable once used; new edits create a new version with an effective period (scenario 14).
- **Locking:** status per assessment/course: `draft → submitted → approved → signed`; reopen only by role with reason (F10).

---

## 12. Later ERP / SIS integration

| Option | Pros | Cons | When |
|---|---|---|---|
| **File-based exchange (Excel/CSV with a documented format)** | Works with any ERP today; no access needed | Manual | Release 1 |
| **REST API with OpenAPI spec** | Standard; auto docs; any ERP can call it | Security, keys, rate limits to manage | Release 2 |
| **Webhooks** (we notify the ERP on results signed) | Near real-time | ERP must accept them | Later |
| **Standards: IMS OneRoster** (rosters, results), **LTI** (launch from an LMS like Moodle), **CASE** (outcomes frameworks) | Reusable across vendors | Few Indian college ERPs support them | Later |
| **Connectors per ERP** (adapters) | Exact fit per college | One per ERP; maintenance | On demand |
| **Direct database reads** from the ERP | Quick | Fragile, insecure; avoid | Avoid |

- **Prepare now (cheap):** keep an `external_id` per student, course, faculty; keep import code behind an "adapter" layer; no ERP-specific fields in the core.

---

## 13. Full-stack combinations compared

Each row is a complete, realistic way to build release 1. Scores: 1 (poor) to 5 (best).

| # | Combination | Fit to reqs | Ease for students | Free hosting fit | Engine / decimals | Excel / reports | Tenancy & audit | ERP-ready | Total /35 |
|---|---|---|---|---|---|---|---|---|---|
| A | **Django + Postgres + templates/HTMX + one JS grid** (modular monolith) | 5 | 4 | 4 | 5 | 5 | 5 | 4 | **32** |
| B | **Django (API) or FastAPI + React SPA + Postgres** | 5 | 3 | 4 | 5 | 5 | 4 | 5 | **31** |
| C | **Next.js (TypeScript) full stack + Postgres (Prisma/Drizzle) + Auth.js** | 4 | 3 | 4 | 3 | 4 | 4 | 4 | **26** |
| D | **NestJS/Express + React + Postgres** | 4 | 3 | 4 | 3 | 4 | 4 | 5 | **27** |
| E | **Supabase (DB, auth, RLS) + React SPA + engine in the browser or edge functions** | 3 | 3 | 3 | 3 | 3 | 4 | 3 | **22** |
| F | **Spring Boot + React + Postgres/MySQL** | 5 | 2 | 2 | 5 | 4 | 5 | 5 | **28** |
| G | **Laravel + Blade/Livewire + MySQL** | 4 | 3 | 2 | 4 | 4 | 4 | 4 | **25** |
| H | **Cloudflare Workers + D1 + SPA** (serverless) | 3 | 2 | 4 | 3 | 2 | 3 | 3 | **20** |
| I | **Low-code (Appsmith/Budibase) or Google Sheets + Apps Script** | 2 | 5 | 4 | 1 | 3 | 1 | 2 | **18** |
| J | **Any of A/B packaged in Docker, self-hosted per college** (deployment variant) | 5 | 3 | 5 | 5 | 5 | 5 | 4 | **32** |

Notes:
- Scores assume a team comfortable in Python. If the team already knows Java well, F rises; if JavaScript, C/D rise by 1 to 2 points.
- The engine choice (section 4) is independent of the stack; **4.2 config-as-data catalogue** is assumed for every row except I.

### Engine approaches compared
| Approach | No-code config | Explainable | Safe | Matches workbook easily | Effort |
|---|---|---|---|---|---|
| 4.1 Hard-coded + settings | No | Yes | Yes | Yes | Low |
| **4.2 Building-block catalogue (config as data)** | **Yes** | **Yes** | **Yes** | Yes | Medium |
| 4.3 Free formulas | Partly | Partly | Risky | Yes | Medium |
| 4.4 Rules engine | Partly | Partly | Yes | Hard | High |
| 4.5 Excel as engine | Yes | No | No | Yes | Medium |
| 4.6 SQL | No | No | Yes | Medium | Medium-High |

---

## 14. Tentative recommendation (NOT a decision)

**Tentative, to be confirmed after your answers in section 15.**

- **Architecture:** modular monolith (1.2), with the **calculation engine as a pure, separately tested library**.
- **Engine:** config as data (4.2): a catalogue of building-block steps with parameters, saved as versioned JSON validated by a schema; a tiny safe expression evaluator only for weighted combinations (4.3 inside 4.2); exact decimals everywhere; on-demand calculation plus frozen snapshots at sign-off.
- **Stack (if the team knows Python):** combination **A**: Django + PostgreSQL + server templates with HTMX + AG Grid Community (or a plain table) for marks entry; openpyxl for Excel; browser print CSS and/or WeasyPrint for PDF; Chart.js for charts; django-simple-history plus an app-level reason log for audit.
  - Fallback if the team prefers JavaScript: **D** (NestJS + React + Postgres) with `decimal.js`.
- **Tenancy:** shared tables with `college_id`, enforced in one place in code; add Postgres row-level security later if time allows.
- **Auth:** built-in framework auth with scoped roles; Google sign-in as an optional extra.
- **Hosting:**
  - Development/demo: app on Render free (accept the 1-minute wake-up) or an Oracle Always Free VM; database on **Neon free** (not Render Postgres, which is deleted after 30 days); nightly `pg_dump` backup via GitHub Actions; anonymised data only.
  - Real college use: **Docker image self-hosted by the college** (J), so student data stays with them and no free-tier limit applies.
- **Integration:** Excel/CSV formats in release 1; external-id fields now; REST API with OpenAPI in a later release.

**Why (short):**
- Fewest moving parts for a student team; one deploy fits free tiers.
- Django admin gives the many setup screens (F1 to F5) almost for free.
- Python has the best Excel and decimal support for matching the workbook exactly.
- The engine stays independent, so it can be tested against Appendix A/B and reused if the stack ever changes.

**Main risks of this recommendation:**
- Free hosts sleep (slow first load) and change terms; mitigated by self-hosting for real use and by backups.
- HTMX pages feel less "app-like" than React; mitigated by using a JS grid only where needed.
- The building-block catalogue may miss a future college's method; mitigated by testing it against two published methods on paper (scenario 16) before coding the UI.

---

## 15. Questions for you
1. **Team:** how many people, and which languages/frameworks do they already know well (Python, Java, JavaScript, PHP)?
2. **Timeline:** when is the first demo, and when is the final submission?
3. **Who hosts real data:** one central website for all colleges (we run it), or each college installs its own copy? Or demo only for now?
4. **College server:** can Vasavi (or the pilot college) give a server or VM for hosting?
5. **Sign-in:** do staff have college Google Workspace (or Microsoft) accounts we can use for sign-in?
6. **Internet:** must marks entry work offline, or is internet always available?
7. **Devices:** will lecturers use laptops only, or also phones for marks entry?
8. **Excel formats:** should exports reproduce the mentor's exact sheet layouts, or is a clean layout with the same content acceptable?
9. **PDF:** are signed PDF reports required in release 1, or is print-from-browser enough?
10. **Credit card:** is anyone willing to register a card for "free" tiers that require one (Oracle, Google Cloud)? If not, those options drop out.
11. **Licence:** will this stay a free/open-source project, or could it be sold later? (Affects Handsontable, HyperFormula, Vercel Hobby.)
12. **Mentor review:** can the mentor review the building-block list (section 4.2) before we build, to confirm it covers their method?

---

## Sources (checked 2026-11-06)
- Neon free plan limits (official, updated 2026-10-01): https://neon.com/faqs/free-plan-limits-and-quotas
- Render free tier (official): https://render.com/docs/free
- Cloudflare D1 free-tier enforcement (official changelog, 2026-09-01): https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/
- Cloudflare Workers pricing summary (third-party, 2026-11-03): https://www.activepieces.com/blog/cloudflare-workers-pricing-2026-free-vs-paid-plans.md
- Supabase free limits (third-party, 2026-06): https://automationatlas.io/answers/supabase-free-tier-limits-2026/
- Oracle Always Free reduction (third-party, 2026-06-14): https://braindetox.kr/en/posts/oracle_always_free_tier_reduced_2026.html
- Library licences (AG Grid MIT/Enterprise, Handsontable non-commercial, HyperFormula GPLv3, SheetJS CE) are from general knowledge; verify on each project's site before use.
