# Active Context

## Current focus
Repo scaffold only: Claude Code files, CI, ADRs, memory bank, README, ROADMAP. No application code yet. Next: v0.1.0 (foundation and tenancy) from `ROADMAP.md`.

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

## Environment notes
- Write files as UTF-8, no BOM, LF endings.
- `gh` auth may be unavailable in cloud sessions; check CI with the GitHub MCP tools.
- Real mentor workbooks only in gitignored `data/private/`; committed fixtures are anonymised.

## Next step
Start v0.1.0 with `/new-feature`: pyproject and uv lockfile, Django project with `config/`, Docker and Compose with PostgreSQL, tenancy base (college_id, RLS, isolation test), CI with a PostgreSQL service. Then update `progress.md`.
