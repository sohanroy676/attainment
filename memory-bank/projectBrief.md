# Project brief

## What and who
Attainment: a free, configurable web app that automates OBE (outcome-based education) CO/PO attainment for any college. Lecturers only enter marks per roll number; everything else is automatic, explainable and audited. Built for lecturers, HoDs, IQAC/accreditation coordinators and principals. Reference college: Vasavi College of Engineering (Deep Learning course, 67 students; CSE 2021-25 batch).

## Goal
v1.0.0 = the prototype: all 20 acceptance scenarios pass, reproducing the mentor's workbooks (section 3 of `ROADMAP.md`: R1 to R4), for one college with several departments, sections and batches.

## Success criteria
- Reference results match exactly: R1 (strict 60%, course 2.18 Not attained) and R2 (typed Internal-II overrides, course 2.32 Attained), plus the CSE 2021-25 batch roll-up.
- Any college can change levels, thresholds, weights, tools and rounding as configuration, with no code change.
- Every number can be traced back to marks, with the method version and engine version recorded.
- A lecturer enters or pastes marks by roll number (gaps and dropouts allowed); nothing else is typed.
- One college can never see another's data.
- Runs on free tools only; a college can self-host with Docker.

## Out of scope (for now)
- Connecting to a college ERP/LMS (planned later, v1.4 REST API).
- Indirect surveys before v1.3 (indirect CO is an entered value of 3 until then).
- Paid services, mobile app, SSO and translations (v1.5).
- Real student data in the demo or in the repo.
