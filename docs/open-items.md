# Open items (v1.0.0)

Each item has an owner and the version where it is needed. "Owner" is the person who has to decide or supply something; nothing here is silently assumed.

| Item | Owner | Needed by | State today |
|---|---|---|---|
| Real Deep Learning workbook as DS-A (`scripts/build_ds_a.py`) so R1 (2.18) and R2 (2.32) run on real data | Owner | before the parallel run | golden tests skip with that reason; scenario 1 passes on hand-worked synthetic numbers |
| CSE 2021-25 batch workbook as DS-B (`scripts/build_ds_b.py`) for R3 and the course counts | Owner | before the parallel run | golden batch tests skip |
| Two published methods from other colleges (DS-E) | Team | v1.2.0 (or v0.3.0 A10) | scenario 16 uses the worked second method in `docs/examples/method-college-b.json` |
| Is Internal-II "answer any 4 of 6"? | Mentor | rules guide sign-off | configured as best 4 of 6; levels do not change on the reference data |
| Official result: strict 60% (2.18) or approved typed pass marks (2.32) | College IQAC and mentor | before the parallel run | default is strict; overrides available |
| Target revision rule (+0.5 points, +0.5%, x1.1) | Mentor | v1.2.0 | targets are set by hand; the proposal screen is not built |
| Under-18 students and consent for academic records | College | before real data | the privacy notice template has a placeholder |
| Report layouts compared with the mentor's documents | Mentor and team | M1 of v0.10.0 | layouts follow the design, not yet the documents |
| Rules guide sign-off | Mentor | v1.0.0 M5 | `docs/rules-guide/README.md` lists seven questions |
| Free demo hosting (Render, Neon) and its limits | Owner | demo deployment | not deployed; limits to be re-checked on the vendors' pages |
| Retention period and notice wording | College | before real data | defaults 5 years and 30 days |
| Indirect survey workbooks | Mentor | v1.3.0 | indirect is an entered value |
| Manual tests M1 to M5 of every version from v0.1.0 | Owner | release gates | none run independently |
| Push the stacked branches, one PR each, CI, tags | Owner | release gates | nothing is pushed |
| Spreadsheet-style marks grid with paste (Jspreadsheet CE) and its browser test | Team | later in v1.0.x | a form grid and an Excel template exist |
