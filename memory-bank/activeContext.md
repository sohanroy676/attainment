# Active Context

## Current focus
v0.2.0 to v0.4.0 are built locally as stacked branches (no push yet; owner runs manual tests later, all at once). Next build: v0.7.0 (results and explanations: CalculationRun, ResultValue, Explain screens; R1 and R2 on screen).

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

## Environment notes
- Write files as UTF-8, no BOM, LF endings.
- `gh` auth may be unavailable in cloud sessions; check CI with the GitHub MCP tools.
- Real mentor workbooks only in gitignored `data/private/`; committed fixtures are anonymised.

## Next step
Build v0.5.0. Owner later: build DS-A and DS-B, run golden tests, run all manual tests (v0.2.0 M1-M4, v0.3.0 M1-M4, v0.4.0 M1-M5, v0.1.0 M1-M5), then push the stacked branches in order, one PR each.
