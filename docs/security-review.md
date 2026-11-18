# Security review (v0.11.0)

A checklist against common web risks. "Evidence" names the automatic test or the file that shows it. Items marked **manual** still need a person.

| # | Risk | Control | Evidence |
|---|---|---|---|
| 1 | One college reading or changing another's data | `college_id` on every tenant table, forced row-level security, `SET LOCAL` per request, app role without bypass | `apps/tenancy/tests/test_rls.py`; `test_sweep.py` requests every discovered record endpoint with GET and POST as six users of another college (zero leaks, nothing changed) |
| 2 | Broken access control inside a college | One permission service, scope-aware checks, lecturers confined to their sections | `apps/accounts/tests`, `apps/reports/tests` (access by role), per-version isolation tests |
| 3 | Injection | ORM everywhere; no SQL built from input; ruff `S` rules (bandit) on every push | CI lint job |
| 4 | Cross-site scripting | Django auto-escaping; Content-Security-Policy; uploads served as attachments with a sandbox CSP; SVG written by code from escaped text | `apps/accounts/tests/test_auth.py`; `apps/reports/tests` (chart escaping) |
| 5 | Cross-site request forgery | Django CSRF middleware on every form and POST | framework default (`CsrfViewMiddleware`); not separately tested because the test client skips CSRF by default. **manual:** try a POST without the token |
| 6 | Broken authentication | Argon2, 10+ characters, common and numeric passwords refused, lockout after 5 failures, 30 minute idle timeout, secure cookies | `test_auth.py`, `test_v0110_hardening.py` (lockout) |
| 7 | Rate limits and abuse of heavy endpoints | per-user limits on PDF rendering, uploads and full export (429 with Retry-After) | `test_v0110_hardening.py` |
| 8 | Malicious uploads | size and type checks by content, 5000-row limit, entity-expansion attack refused (defusedxml), decompression bomb refused from the zip directory, formulas never evaluated, proof files PDF/PNG/JPEG by their bytes, cap per college | `test_marks_import.py`, `test_v0110_hardening.py` |
| 9 | Vulnerable dependencies | `pip-audit` on the locked set in CI; Dependabot | CI `dependencies` job; local run found none |
| 10 | Secrets in code or images | secrets only in `.env`; gitleaks on full history in CI; `.dockerignore` excludes `.env`, `data`, `backups`; no secret ENV or ARG in the Dockerfile | CI `secrets` job; `test_ops.py` |
| 11 | Container hardening | non-root user; production overlay: read-only file system, no new privileges, all capabilities dropped, database port not published | `test_ops.py` (static checks); **manual** `docker history` and scan on the release image |
| 12 | Tampering with records | audit log append-only (trigger plus revoked grants), hash-chained per college, nightly verify command; signed runs and published methods frozen by triggers; approved marks locked by trigger | `test_audit.py`, `test_v0110_hardening.py`, v0.5.0 and v0.8.0 tests |
| 13 | Data loss | encrypted backups, checksum, restore script refusing wrong keys, scheduled restore test | `test_ops.py` restores a real dump and compares every table |
| 14 | Personal data exposure | audit log holds ids not names; retention with notice and anonymising; per-student export (audited); logs hold ids | `apps/privacy/tests` |
| 15 | Security headers and transport | HSTS, secure cookies, `check --deploy` at warning level in CI, HTTPS by Caddy | CI deployment-check step; `test_auth.py` |
| 16 | Information leakage in errors | 404 for another college's records (not 403); no stack traces in production (`DEBUG` off) | sweep (403/404 only) |
| 17 | Outside file access in reports | report renderer refuses every address except `data:` | `test_reports.py` |

## Not covered by a test
- **Manual:** a penetration test or a review by someone other than the author; a scan of the built image; reading the production `.env` permissions on a real server.
- The rate limits are per process (see `docs/known-limits.md`).
- Backups are only as safe as where they are copied; the passphrase must be kept apart (admin guide section 4).
