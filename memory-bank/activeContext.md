# Active Context

## Current focus
v0.1.0 (foundation and tenancy) is implemented on branch `feature/v0.1.0-foundation`, not pushed. Next: push with approval, watch CI, run M1 to M5, release gate, tag. Then v0.2.0 (engine) per `memory-bank/next_session_prompt.md`.

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

## Environment notes
- Write files as UTF-8, no BOM, LF endings.
- `gh` auth may be unavailable in cloud sessions; check CI with the GitHub MCP tools.
- Real mentor workbooks only in gitignored `data/private/`; committed fixtures are anonymised.

## Next step
With approval, push the branch, watch CI, run M1 to M5, tag v0.1.0. Then start v0.2.0.
