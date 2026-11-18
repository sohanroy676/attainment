# Demo script (mentor walk-through, v1.0.0 manual test M1)

Setup, once: `docker compose up -d`, then
```
docker compose exec app python manage.py seed_demo
docker compose exec app python manage.py seed_demo_course
```
`seed_demo` prints the demo password once; `seed_demo_course` prints the address of each college's course page. Demo college A numbers rolls 1.. in each of two sections (40 + 27 students); demo college B numbers 1-66 and 67-130 across the batch. All names and marks are invented.

Use two browsers or private windows so you can be two people at once. Users are `a.iqac`, `a.hod`, `a.coordinator`, `a.lecturer`, `a.exam`, `a.principal`, `a.auditor` (and the same with `b.`).

| # | Do this | Look for |
|---|---|---|
| 1 | Log in as `a.iqac` | The home page lists the role; "My tasks" |
| 2 | Open **Methods** (`/methods/`) and the Vasavi method version | Version number, content hash, status "active"; the version cannot be edited |
| 3 | As `a.iqac` or `a.coordinator`, open the course page (address printed by `seed_demo_course`). Under "Set-up" open the Deep Learning paper and the CO-PO map (the map link is for `a.iqac`) | Parts with maximum marks and COs; choice group on the semester paper; mapping grid with 1 to 3 |
| 4 | As `a.lecturer`, open the Internal-I grid for section A (from the course page of the coordinator, or `/marks/<assessment>/<section>/`); change one mark and save | "Saved 1 marks"; the cell has a history link (h) |
| 5 | As `a.iqac`, open the course page (address printed by `seed_demo_course`) | Levels per tool, direct, indirect (entered, not measured), final, course attainment, target, status |
| 6 | Click three numbers (a tool percentage, a final CO, the course) | Explain: pass counts, denominator, method and engine version, input fingerprint |
| 7 | Open **Gaps** | COs under target, the weakest question parts |
| 8 | As `a.coordinator`, open the paper of Internal-II from the course page's Set-up links and propose a pass mark of 2 for a part, with a reason; as `a.iqac` approve it | The paper shows it approved; the result recalculates by itself; the report lists the override |
| 9 | Compare the course attainment before and after step 8 | The number changes; every change is in the audit log (`/workflow/audit/`) |
| 10 | Coordinator: **review**; `a.hod`: **approve**; `a.principal`: **sign** (My tasks, then the course stage page) | Signature records with name, role, time and hash |
| 11 | As `a.lecturer`, try to change a mark of the signed result | Refused (the marks are locked) |
| 12 | Open the **batch** page (`/results/batch/<batch>/`, from the course page's programme) | PO and PSO totals, status against target, core and non-core counts, courses left out |
| 13 | On **Compare**, look at the three-batch table and the side-by-side check against an uploaded old workbook | Differences shown at the method's precision |
| 14 | Open **Reports** on the course page: the course analysis as PDF | Footer with college, programme, batch, course, method and engine version, run id, hash; PROVISIONAL watermark only if the result is not complete |
| 15 | Open the audit log as `a.auditor` | Every login, import, override, approval and signature, by person id |

Record the mentor's notes next to each step in `docs/test-reports/v1.0.0.md`.
