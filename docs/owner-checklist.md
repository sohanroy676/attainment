# Owner checklist: what to do before the next session

State: everything through v1.0.1 is merged to `main` and tagged; CI is green. What is **not** done is the part only a person can do: run the app by hand, bring the real workbooks, get the mentor's answers. Do these in order. Write each result down in `docs/test-reports/<version>.md` (who, date, pass/fail, notes). A failed step is a finding, not a problem: tell the next session what you saw.

## 1. Start the app (about 15 minutes)
1. Install Docker Desktop and `uv`. In the repo: `uv sync`.
2. Make the settings file: `uv run python scripts/init_env.py` (creates `.env`). Open it and check `ALLOW_INSECURE_HTTP=true` for a laptop trial. Add the new settings by hand (my tools cannot edit `.env.example`): `RETENTION_YEARS=5`, `RETENTION_NOTICE_DAYS=30`, `BACKUP_PASSPHRASE=` (a long phrase you keep elsewhere), `ADMIN_PASSWORD=` (leave empty to get a generated one).
3. `docker compose up -d --build`, then
   `docker compose exec app python manage.py seed_demo` (prints the demo password once: save it) and
   `docker compose exec app python manage.py seed_demo_course` (prints each demo college's course address).
4. Open `http://localhost`. `/healthz` should say `ok`. (`https://localhost` may not answer on a laptop trial; use `http`.)

If step 3 fails:
- `Bind for 127.0.0.1:5432 failed: port is already allocated`: another Postgres (for example a leftover test container, see `docker ps`) holds the port. Stop it (`docker stop <name>`) or set `DB_PORT=5433` in `.env`.
- `failed to resolve host 'db'`: the db container was created during a failed start and is not on the network. Run `docker compose down`, then `docker compose up -d`.
- `password authentication failed for user "attainment_owner"`: the database volume was created with older passwords than the current `.env`. PostgreSQL only sets passwords when a volume is first created. If the database holds nothing you need, run `docker compose down -v` (deletes the volumes), then `docker compose up -d`.
**If something fails here, stop and tell the next session; do not work around it.**

## 2. Walk the demo (about 45 minutes; this is v1.0.0 M1)
Follow `docs/demo-script.md` step by step with two browsers (two people at once). Note for each step: worked / did not / confusing. Pay special attention to: finding your way without a menu, the Explain panels, the PROVISIONAL watermark, the pass-mark override flow, signing and then trying to edit.

## 3. Check the printed reports (about 30 minutes; v0.10.0 M1, M3, M4)
From the course page open Reports and download each PDF and Excel file. Print one on A4. Check: signature blocks have room, nothing is cut off, the footer fields are all there, numbers equal the page. Compare each report with the mentor's own documents section by section and list the differences (this is the input for matching the college's layouts).

## 4. Try a new user (v1.0.0 M2, v0.11.0 M5)
Ask a lecturer who has never seen the app to enter one section's marks using only `docs/user-guide.md`, while you watch and say nothing. Write down every place they stop.

## 5. Try to break it (about 30 minutes)
- Log in as `b.iqac` (the other demo college) and open an address of college A's course page: it must say not found.
- As the lecturer, try to edit a mark after the result is signed: it must refuse.
- Upload a wrong file as marks (a PDF renamed `.xlsx`, a sheet with a mark above the maximum): it must refuse the whole file and say which row.
- Stop the app container (`docker compose stop app`) in the middle of uploading a roster, start it again: no half-imported roster (v0.11.0 M3).

## 6. Backups (v0.11.0 M2): prove you can restore
1. `BACKUP_PASSPHRASE='...' scripts/ops/backup.sh`, then copy the file off the machine.
2. `BACKUP_PASSPHRASE='...' scripts/ops/restore_test.sh`: must end with "restore test passed".
3. Optional but valuable: delete the demo database volume, restore into the live database following `docs/admin-guide.md` section 4, and confirm the signed demo result looks unchanged.

## 7. The version-by-version manual tests still owed
Each version's M-tests are in `ROADMAP.md` (search for the version heading, then "Manual tests"): v0.1.0 M1-M5, v0.2.0 M1-M4, v0.3.0 M1-M4, v0.4.0 M1-M5, v0.5.0, v0.6.0, v0.7.0, v0.8.0, v0.9.0, v0.10.0 M1-M5, v0.11.0 M1-M6, v1.0.0 M1-M5. Many overlap with sections 2 to 6 above. Do not repeat the ones you already covered; record which M-test each walk-through satisfied.

## 8. Bring the real data (needed to prove the numbers)
These stay on your machine in the gitignored `data/private/` folder; **never commit them, never paste them into a chat**.
1. Put the Deep Learning workbook in `data/private/` and run `uv run python scripts/build_ds_a.py`; check the output is anonymous (no names, no real roll numbers) before it is committed. Then `uv run pytest -m golden`. Expected: R1 course 2.18 Not attained; R2 (with the college's typed Internal-II pass marks as overrides) 2.32 Attained.
2. Do the same with the CSE 2021-25 batch workbook: `scripts/build_ds_b.py`, expected R3 (PO totals in `ROADMAP.md` section 3).
3. If a golden test fails, do not edit the test: send the failure to the next session. A change to a golden result needs a written reason and a minor version bump.

## 9. Questions only the mentor and the college can answer
Take `docs/rules-guide/README.md` ("Questions for the mentor") and `docs/open-items.md` to the mentor. Get answers to: is Internal-II "answer any 4 of 6"; which result is official (2.18 or 2.32); what the target revision rule is; whether the typed pass marks are acceptable; consent for under-18 students; how long records are kept (default 5 years then 30 days notice). Ask the mentor to sign off the rules guide (v1.0.0 M5).

## 10. Housekeeping on GitHub and the server
- Turn on branch protection for `main` (require the CI checks; no direct pushes). In Settings, Code security: confirm secret scanning and Dependabot alerts are on.
- If you want the free demo online (Render, Neon): re-check the vendors' current free-tier limits first; follow `docs/admin-guide.md`; use only anonymised data.
- Decide whether the paste-from-Excel script in the marks grid is enough, or whether you still want the Jspreadsheet component.

## 11. Tell the next session
Open a new Claude Code session and say: "Read `memory-bank/next_session_prompt.md` and continue." Give it: the list of failed or confusing steps from sections 2 to 6, the golden test output from section 8, and the mentor's answers from section 9.
