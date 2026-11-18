# Active Context

## Current focus
v0.2.0 to v0.4.0 are built locally as stacked branches (no push yet; owner runs manual tests later, all at once). v0.8.0 (workflow and governance) and v0.9.0 (department, batch and quality loop) are built and verified locally. v0.10.0 (reports and exports) and v0.11.0 (hardening, privacy, operations) are built locally on stacked branches `feature/v0.10.0-reports` and `feature/v0.11.0-hardening`. Next: release gates, then v1.0.0 (the 20 acceptance scenarios, demo data, guides).

## Decisions (settled, do not re-ask)
- Stack: Python 3.12, uv, Django 5.2 LTS, PostgreSQL 16+, HTMX; pure `engine/` package with `Decimal` (ADRs 0002 to 0004).
- Pass rule: strict 60% of max per part; per-part override allowed with a reason (ADR 0008).
- Rounding: configurable per level (round or truncate); compared value default unrounded.
- Denominator: configurable per question or choice group; for choice questions count only students who attempted it; compulsory = all who sat.
- Below 10% = stop for review (provisional); a tool with no value for a CO = stop for review.
- Supplementary/improvement attempts count as a regular attempt only.
- Licence MIT. Demo on free cloud with anonymised data; colleges self-host real data.
- Marks grid: Jspreadsheet CE (fallback Tabulator). Not AG Grid Community (paste is Enterprise-only).
- No time estimates anywhere in the roadmap.

## Open items
- Target revision rule: manual until the mentor decides.
- Which result the college treats as official: 2.18 (strict) or 2.32 (overrides).
- Confirm with the paper that Internal-II is "answer any 4 of 6".
- Under-18 consent under DPDP: assumed exempt for the demo; confirm with the college before the pilot.
- Two published methods are needed before v0.3.0 test A10.
- Re-check free-tier limits (Render, Neon) before deploying the demo.
- Indirect survey workbooks are needed for v1.3.0.

## v0.1.0 design choices (settled)
- Two DB roles: `default` = non-owner app role; `owner` alias runs `migrate --database owner`. Grants to the app role are applied by a `post_migrate` handler in `apps/tenancy/apps.py` (no TRUNCATE; audit table loses UPDATE and DELETE).
- `TenantMiddleware` opens its own transaction and sets `app.college_id` with `set_config(..., true)`. Django's ATOMIC_REQUESTS alone starts too late (after middleware), so the middleware wraps the request. The college comes from the session key written at login.
- Pre-login lookups (login, password reset) see exactly one user row via `app.auth_login` / `app.auth_user_id` in the users RLS policy. Username is unique across all colleges.
- Lockout is per username only (axes.W006 silenced): behind the proxy all clients share one IP.
- Tests: `config/settings/test.py`, database `attainment_test` created by the PostgreSQL superuser, migrated by the owner, used as the app role. Use `committed_db` for tests that need real commits; the owner truncates afterwards. Needs `POSTGRES_*` and `DB_*` env vars (from `.env` via `scripts/init_env.py`, or the shell).
- Demo accounts: `a.` and `b.` + admin, iqac, hod, coordinator, lecturer, exam, principal, auditor. Design section 2.5 does not list demo accounts; the set is derived from the section 9 role table.

## Open items from v0.9.0
- Target-revision proposal (manual by default) is not built; needs the mentor's rule.
- Action Taken Report (design 8.9 step 3) belongs with v0.10.0 reports.
- Old-workbook comparison is batch level only (PO direct and total); course-level CO comparison (A6 and M3 at course level) is not built.
- Batch sign-off tasks are not in the workflow inbox; observations and plans cannot be edited.
- A1 and A5 against the real mentor files (R3, chart table) need DS-B and the old workbooks.
- Free-tier database size may need a lower proof-file cap than 200 MB.

## Open items from v0.1.0
- Platform admin (no college) is not implemented: users must belong to a college.
- Failed logins are not audited (college unknown before login); successful login, logout, password reset and role changes are.
- Scope containment (department covers its sections) waits for the academic structure in v0.4.0.
- `.env.example` is blocked for the Read/Write tools by a permission rule; edit it by hand if needed.

## v0.2.0 engine design choices (settled)
- Method config uses objects for bands (`{"min_pct","level","label"}`), not the design's abbreviated arrays; choice rules are keyed by the paper's `choice_group` id: `"choice": {"G": {"best_n": 5, "best_k_parts": {"17": 2}}}`. A part with a `choice_group` but no rule is still a choice question for the `by_choice` denominator (Internal-II).
- Stopped-for-review (`blocked`) values never reach later steps as numbers: direct and final become `blocked`, the run is provisional (`complete=False`), and course attainment is computed from the COs that do have a value.
- A student absent for the whole assessment: marks typed for them never count. `exclude` removes them from denominators, `count_as_fail` keeps them in with no passes.
- Engine arithmetic runs at 40 digits in an explicit `Context`; tests compute expected values at the same precision (`engine/tests/conftest.py`).
- Golden data: `engine/tests/golden/ds_a/course.json` built by `scripts/build_ds_a.py`; R2 is R1 plus overrides of 2 for every 3.5-mark Internal-II part, added in the test.
- A3 (per-question pass counts equal the workbook's own) and A4/A5 level checks on real data are only possible with the real workbook; synthetic analogues exist.

## v0.3.0 and v0.4.0 design choices (settled)
- Method schema additions: `rollup`, `po`, `batch`, `targets` (revise rule, near_target_margin), per-level `precision` with `none` mode, tool `aggregate` (`marks_weighted`, `student_level`). Engine version 0.3.0.
- A blocked or stopped-for-review input is never ignored by a roll-up: it blocks the result.
- Batch input is plain per-course PO values (blank skipped, 0 counted); `course_for_batch` turns a course result into one. DS-B counts per category need category data the workbook layout does not give (left empty).
- `University` is a tenant-owned record (each college records its affiliation) so every table keeps `college_id` and RLS.
- Roll-number uniqueness: identifiers carry a scope (section, batch or whole college); uniqueness is enforced only among current identifiers (no end date) via partial unique indexes. History rows (valid_to set) may repeat.
- Section change: the enrolment's section decides where marks count; the old `SectionMembership` is closed, never deleted.
- Role containment: `accounts.services.register_scope_resolver`; academics registers one so department and programme roles cover their sections. `sections_visible_to(user)` is the access query for lecturers.
- Django admin is the setup UI. `User.is_staff` and `has_perm` delegate to the one permission service (`structure.manage`, `roster.manage`). Admin logs through `AuditedModelAdmin`, not Django's LogEntry.
- Roster import stores parsed rows in `ImportBatch.payload` (personal data; tenant-protected, excluded from audit). Any row error rejects the whole file; confirm re-plans and refuses if the roster changed since the preview.

## v0.5.0 design choices (settled)
- A paper's choice groups live on the paper (`ChoiceGroup`); the engine takes them inside the method tool config (`choice: {group: rule}`). The results module (v0.7.0) must inject `assessments.services.engine_choice_rules(paper)` into the tool config, for tools where the method says to apply them (R1 does not apply Internal-II best 4 of 6; the variant that does gives CO5 46.12). `engine_parts(paper)` gives the engine's part dictionaries; `approved_overrides(offering)` only ever returns approved overrides.
- Part code (`QuestionPart.code`) is the engine part id, unique within the paper; label is display only.
- Method versions: the exact JSON text is stored (`config_text`); `content_hash` is SHA-256 of the canonical form, set at activation. A DB trigger makes published versions immutable (only active to retired plus `effective_to` may change) and undeletable.
- Method resolution: levels university, college, programme, course; most specific wins; a locked wider level always wins; assigning below a locked level is refused. Date for an offering defaults to its academic year's start date.
- `User.ADMIN_PERMISSION` maps admin app labels to permissions (outcomes: `outcomes.edit`, assessments: `paper.edit`, methodology: `method.edit`).

## v0.6.0 design choices (settled)
- `MarkCell` unique per (row, part); `row_version` increments on each real change; `save_cell(expected_version=...)` refuses stale saves with `StaleCell`. `expected_version=0` means "no value yet". Saving an unchanged value does nothing (no version, no history).
- `MarkChange` is append-only for the app role (revoked UPDATE/DELETE plus trigger); `marks_markchange` is in `APPEND_ONLY_TABLES` in `apps/tenancy/apps.py`.
- Permissions: SEE needs `marks.enter_see` (exam branch, college-wide), other assessments `marks.enter_internal` over the section; reading also allowed with `reports.view` over the section (auditor, HoD). `save_cell` checks the right for the enrolment's section.
- Imports: any error rejects the whole file; blank cells on a blank stay untouched; marks sheets carry a `meta` sheet (assessment and section ids) to catch the wrong sheet; script mapping files may carry a `section` column where roll numbers repeat across sections.
- Engine adapter `marks.services.engine_assessment(assessment, sections, state_map)`: default maps value to entered, absent to absent, everything else to blank; a student whose every cell is absent is `absent_whole`.
- Parser safety: broad catch at the file boundary, defusedxml for XML attacks, formulas without cached values refused with the cell named.

## v0.7.0 design choices (settled)
- `results.services.calculate(offering, programme)` builds the input through other modules' services, runs `engine.run_offering` (all sections of that programme, rolled up per the method's `rollup`), and stores a `CalculationRun` (outputs JSON, trace JSON, checklist) plus `ResultValue` rows. Latest non-kept run is replaced; `snapshot()` keeps one. Run per programme: an offering serving two programmes gets two independent runs.
- Choice rules come from the method JSON (`tools.X.choice`), not from the paper's `ChoiceGroup` (the paper's groups drive the `by_choice` denominator tag and validation). R1 therefore applies best-N only where the method says so.
- Provisional = engine `complete` is false OR the checklist is non-empty (no method, no paper, students without a marks row, missing target, missing indirect, empty map, blocked values).
- Recalculation: signals in `apps/results/signals.py` call `mark_dirty`; `transaction.on_commit` registers a flush every time (idempotent). A rolled-back transaction leaves stale entries, which are harmless. Failures are logged, never raised into the saving request.
- Pages need `reports.view` over the offering (course) or section; the lecturer therefore sees section pages only. Explain filters trace entries by the viewer's section permissions. `indirect.enter` (IQAC) is the new permission for indirect values.
- Not built yet in v0.7.0: round/truncate switch in the interface (it is the method's precision), band-edge marker is on tool percentages only.

## v0.8.0 design choices (settled)
- `apps/workflow`: `SectionState` (per section and assessment), `ResultStage` (per offering and programme, with `cycle`), `Signature` (approval and signature records), `Reopening`, `SupportGrant`. Transition tables in `machine.py`.
- Approve keeps a snapshot run and refuses a provisional result; it locks every paper of the offering (assessment status approved). Sign seals the run (`results.seal`, `signed` and `content_hash` on `CalculationRun`; triggers freeze the run and its values, only `is_latest` may change). Reopen: `data.reopen` plus reason, cycle+1, new run, unlock unless another programme's stage is still locked.
- `marks_markcell` has a DB trigger refusing writes on approved or locked assessments. SEE is submitted by `marks.enter_see` (exam branch).
- Overrides (per-part pass marks, ADR 0008) are refused after approval in `assessments.services`.
- Open: department-scoped audit viewer for HoD (viewer is college-wide only), enforcement of `SupportGrant` (needs platform-admin role), "overridden" marker on result pages (M3), email reminders (out of scope).
- `decide_override` checks `override.apply` over the offering's scope, so a department HoD can decide for their own offerings.

## v0.9.0 design choices (settled)
- Batch roll-up lives in `results` (`BatchRun`, `BatchIndirect`, `HistoricResult`): `calculate_batch(batch, include_unsigned, keep)` takes each course's signed run; with `include_unsigned` an unsigned course uses its newest run, but a signed run always wins. Left-out courses, unsigned or provisional courses, missing targets or indirect values keep the batch provisional (checklist). A course run covers all of a programme's sections of the offering, so an offering with sections of two batches counts in both (a checklist line says so). The batch method is the programme's method for the first offering.
- Batch sign-off in `workflow` (`BatchStage`, `BatchSignature`, `BatchReopening`, `BATCH_MOVES`): IQAC prepares (kept, complete, signed-only run), HoD approves, principal signs (`results.seal_batch`; the database freezes the signed run, only `is_latest` may move). Reopen needs `data.reopen` and a reason, cycle+1. Permission scope is the programme. Batch tasks are not in the inbox yet.
- Earlier batches: `HistoricResult` (kinds `po_direct`, `po_total`) imported by `apps/imports/historic.py` (header `Outcome` then `Direct` and/or `Total`; all or nothing; the file is kept as an `ImportBatch` of kind `historic`; a new upload replaces the same kinds and the replaced values stay in the audit log). Three-batch comparison shows signed, else imported, else calculated values per earlier batch. Old-workbook comparison differs only at the method's batch display precision (`engine/compare.py`).
- Gap view: `engine/gaps.py` (`below_target`, `weakest_questions`) reads the stored final values and the `QuestionPass` trace entries; `results.course_gaps` and `results.batch_gaps` feed the pages and the quality draft.
- Quality loop (`apps/quality`): observations, action plans (carry to later offerings of the same course through `previous_plans`), actions taken (later offering only, date not in the future), proof files. Edit right is `observations.edit` over the offering or one of its sections; view is `reports.view` or the edit right. Files: PDF, PNG, JPEG only, type from the file's own bytes, 5 MB each, 10 per action, 200 MB per college (`QUALITY_COLLEGE_MAX_BYTES`), stored in the database, served as attachments with a sandbox CSP. `record_action` saves an action and its files together. No editing or deleting of observations and plans.
- Tests: `apps/tenancy/tests/test_v090_isolation.py` (A12 sweep over every new page and endpoint, plus forced-RLS check), `apps/results/tests/test_batch_speed.py` (A11, marker `perf`). Do not use bare `.first()` on UUID-keyed rows to pick a record in a test.

## v0.10.0 design choices (settled)
- `apps/reports` has no tables. `context.py` arranges stored results (`present`, `present_batch`, `course_gaps`, `comparison_columns`, `quality`, `workflow.signatures_of`); `render.py` picks `reports/<college code>/<name>.html` before `reports/<name>.html` and turns HTML into a PDF (`url_fetcher` only allows `data:`); `excel.py`, `export.py`, `chart.py` (inline SVG).
- Footer: college, programme, batch, course, term, method version, engine version, run id, data status, generated time (`<span data-generated>`, left out when comparing regenerated reports), hash. Signed run: the stored `content_hash`; otherwise the computed hash with a note that it is not signed. Watermark only when the run is not complete.
- URLs: `/reports/course/<offering>/<co_sheet|analysis|co_po|action_taken|appendix>.<html|pdf|xlsx>` (`?programme=` when the course serves two), `/reports/batch/<batch>/report.<fmt>`, `/reports/nba.xlsx` (`reports.view` college-wide), `/reports/export.<xlsx|json>` (`data.export`, audited as `college.exported`). Course reports need `reports.view` over the offering (a section-scoped lecturer is refused, as on the result page).
- Excel cells hold the page's text, so a reopened file equals the page; text starting with "=" is stored as text.
- Full export: every `TenantModel` table, college only; password hashes and binary file contents left out.
- Where PDF libraries are missing the PDF route returns 503 with a message; PDF tests skip. Dockerfile installs `libpango-1.0-0`, `libpangoft2-1.0-0`, `fonts-dejavu-core`.
- Open: layouts follow the mentor's documents (M1); the Action Taken Report embeds PNG and JPEG proofs only (PDF proofs are listed); no real-data golden checks (A3 for R3); the A7 test measures rendering of an in-memory batch, not a 512 MB container.

## v0.11.0 design choices (settled)
- Ops commands that visit every college (`verify_audit --all`, `retention ... --all`) list colleges through a psycopg superuser connection (`apps/tenancy/ops.py`, needs `POSTGRES_USER` and `POSTGRES_PASSWORD`, present only in the `ops` compose profile); with `--college <id>` they use the app role. The college table is forced-RLS, so the app role cannot list colleges.
- Privacy (`apps/privacy`): `RetentionNotice` (one per student). Eligible = every batch ended at least `RETENTION_YEARS` (5) ago; anonymise only after `RETENTION_NOTICE_DAYS` (30). Replaces name and identifier values; marks and enrolments stay; stored upload files and parsed payloads of sections whose batch is past retention are purged (`imports.purge_files`). Permissions: `data.export` and `privacy.manage` (college admin).
- Rate limits are per process (`LocMemCache`): `settings.RATE_LIMITS` name -> (requests, seconds), names `pdf`, `upload`, `export`.
- Backup is one encrypted `pg_dump` (openssl AES-256, pbkdf2) because everything, including proof files, is in the database. `restore.sh` decrypts first and checks the dump's first bytes before touching any database; after restoring the live database run `migrate` to re-apply the app role's grants.
- Tests that need the Docker database container (`test_ops.py`) skip unless `DB_CONTAINER` is set. On Windows `bash` on PATH may be WSL; the test prefers Git's bash.
- Sweep (`test_sweep.py`) fails when a URL has an id parameter it cannot fill: add the model to `ID_MODELS`.
- `college_context` no longer issues SQL in its `finally` after an error broke the transaction.
- PDF tests need GTK3 on Windows: `winget install tschoonj.GTKForWindows`, then `WEASYPRINT_DLL_DIRECTORIES="C:\Program Files\GTK3-Runtime Win64in"`.

## Environment notes
- Write files as UTF-8, no BOM, LF endings.
- `gh` auth may be unavailable in cloud sessions; check CI with the GitHub MCP tools.
- Real mentor workbooks only in gitignored `data/private/`; committed fixtures are anonymised.

## Next step
Build v0.10.0 (reports and exports). Owner later: build DS-A and DS-B, run golden tests, run all manual tests (v0.2.0 M1-M4, v0.3.0 M1-M4, v0.4.0 M1-M5, v0.1.0 M1-M5), then push the stacked branches in order, one PR each.
