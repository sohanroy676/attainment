# Administrator guide

For whoever installs and looks after Attainment for a college. It covers installing, HTTPS, backups, updates, the nightly checks and privacy duties. Nothing here needs a paid service.

## 1. What you are running
Four containers: PostgreSQL 16 (`db`), a one-shot `migrate` job, the web app (`app`) and Caddy (`caddy`, the HTTPS front door). All marks, results, signed runs, proof files and the audit log live in the one database, so **the database backup is the whole backup**.

The database has two logins. `attainment_owner` owns the tables and runs migrations. `attainment_app` serves requests; it cannot bypass row-level security, create tables or change the audit log. The web app never receives the PostgreSQL superuser password. Only the optional `ops` container does (section 6).

## 2. Install on a Linux server
Needs Docker with the compose plugin, `git`, `openssl` and about 2 GB of memory.

1. `git clone` the repository and check out the release tag you are installing.
2. Create the settings file: `uv run python scripts/init_env.py` (or copy `.env.example` to `.env` and fill it in). It writes random passwords for the three database logins and a secret key. Keep `.env` out of version control and readable only by the admin account (`chmod 600 .env`).
3. Set in `.env`: `DJANGO_ALLOWED_HOSTS` (your site name), `SITE_ADDRESS` (see section 3), `ALLOW_INSECURE_HTTP=false`.
4. Start: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
5. Create the college and its first administrator:
   `docker compose exec app python manage.py create_college "Full College Name" short-code first.admin`
   It prints the administrator's password once (or set `ADMIN_PASSWORD` to choose it); change it at first login. Everyone else is added on the Users screen. For a trial with fake data use `docker compose exec app python manage.py seed_demo` instead (demo accounts, never with real data).
6. Open the site. `https://<your name>/healthz` must answer `ok`.

The production file does not publish the database port, runs the app with a read-only file system, drops Linux capabilities and rotates container logs (5 files of 10 MB).

## 3. HTTPS
- **Public name** (for example `attainment.college.edu`, DNS pointing at the server, ports 80 and 443 open): set `SITE_ADDRESS=attainment.college.edu`. Caddy gets and renews a certificate by itself.
- **Internal name** (no public DNS): set `SITE_ADDRESS=attainment.internal` and `CADDY_TLS_DIRECTIVE=tls internal`. Caddy signs with its own authority. Install its root certificate (`caddy_data` volume, `caddy/pki/authorities/local/root.crt`) on the machines that will use the site, or browsers will warn.
- `ALLOW_INSECURE_HTTP=true` is for a laptop trial only. It switches off secure cookies and HSTS.

## 4. Backups
`scripts/ops/backup.sh` writes an encrypted dump (`AES-256`, key from `BACKUP_PASSPHRASE`) plus a checksum to `./backups` and keeps the newest 14.

```
BACKUP_PASSPHRASE='...' scripts/ops/backup.sh
```
- **Keep the passphrase somewhere other than the server** (a password manager, a sealed envelope with the principal). A backup with a lost passphrase is unreadable by design.
- **Copy the `backups` folder off the server** each night (another machine, a college file server). A backup on the same disk does not survive the disk.
- Schedule it with cron, for example `15 2 * * * cd /srv/attainment && BACKUP_PASSPHRASE=$(cat /root/.attainment-key) scripts/ops/backup.sh`.

### Restoring
```
BACKUP_PASSPHRASE='...' scripts/ops/restore.sh backups/attainment-<time>.dump.enc
```
restores into a scratch database `attainment_restore` and touches nothing live. A wrong passphrase or a damaged file stops before any database is changed. To replace the live database: stop the app (`docker compose stop app caddy`), run the script with the live database name as the second argument, run `docker compose run --rm migrate` (this re-applies the app login's privileges), then start the app.

### Prove it works: the restore test
`scripts/ops/restore_test.sh` restores the newest backup into a scratch database, re-applies privileges, checks every college's audit chain and drops the scratch database. Schedule it weekly (`0 4 * * 0 ...`). A backup nobody has restored is not a backup.

## 5. Updating
```
git fetch && git checkout <new tag>
BACKUP_PASSPHRASE='...' COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml" scripts/ops/update.sh
```
It backs up, builds, migrates, restarts and checks `/healthz`. If the migration or the health check fails it restores the backup and the previous image and tells you. Read `CHANGELOG.md` for the release first; a release that changes the method schema says so.

## 6. Nightly checks (the `ops` container)
The `ops` container is the only place the PostgreSQL superuser login appears. It is off unless asked for:
```
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile ops run --rm ops python manage.py verify_audit --all
```
- **verify_audit** recomputes each college's audit hash chain. A non-zero exit means a row was altered or removed: treat it as an incident (section 8). Schedule it nightly and send a failure to someone who will read it.
- **retention** (section 7).

## 7. Privacy duties
Student names and roll numbers are personal data.
- **Retention.** `RETENTION_YEARS` (default 5) after a batch ends and after `RETENTION_NOTICE_DAYS` (default 30) of notice, a student's name and identifiers are replaced. Marks stay so signed results can still be reproduced; stored upload files for those sections are removed. Run, as a monthly routine: `... ops python manage.py retention list --all`, then `retention notify --all`, then, a notice period later, `retention anonymise --all`. The page `/privacy/retention/` shows the same list. Before running `notify` for the first time, decide the retention period with the college and send the notice (template: `docs/privacy-notice-template.md`).
- **A student's request for their data.** `/privacy/student/<id>/export.json` (college admin) gives everything held about one student, including each mark and its change history. Each export is written to the audit log.
- **Full export.** `/reports/export.xlsx` and `.json` give every table of the college (admin only, logged, limited to 5 per hour).
- **Demo and test data** must be anonymised first: `python manage.py anonymise_roster real.csv anonymised.csv` replaces names and roll numbers with `S001`, `Student 001`... Real workbooks stay in the gitignored `data/private/` folder and never go in git.
- **Under-18 students.** The college must confirm whether consent is needed for academic records before real data is loaded (open item).

## 8. If something goes wrong
- **verify_audit reports BROKEN.** Stop changes, keep the database as it is, take a backup now, and compare with an older backup restored to scratch to find the first bad row. Tell the principal. The log is append-only for the app, so a break means someone with owner or superuser database access changed it.
- **A lecturer sees another college's data.** Should be impossible (tested by sweep); take the site down and report it as a security incident.
- **PDFs return "not available".** The Pango libraries are missing (they are in the Docker image). Outside Docker install `libpango-1.0-0` and `libpangoft2-1.0-0`.
- **A user is locked out.** Five wrong passwords lock that username for 15 minutes. Wait, or an admin resets the password.
- **The disk is filling.** Proof files are stored in the database (cap `QUALITY_COLLEGE_MAX_BYTES`, default 200 MB per college). Container logs are rotated.

## 9. Logs
The application writes request and error lines to the container log (rotated, 50 MB at most per container). The code is written so that logs carry internal ids, not passwords, marks, names or roll numbers, and the audit log (in the database) refers to people by internal id; report any line that breaks this. Keep container logs for 30 days; the audit log is kept for as long as the college keeps the records it describes.

## 10. Limits to know
See `docs/known-limits.md`.
