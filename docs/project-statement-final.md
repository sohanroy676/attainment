# Project statement: configurable OBE attainment platform

**Version 2.0 (final baseline for design)** · 2026-11-06
**Purpose:** the single source of requirements to start designing the solution.
**This document contains requirements and business rules only.** It does not prescribe architecture, technology or implementation.

How to read the rule tags:
- **[C]** Confirmed by you or the mentor.
- **[D]** Default I assumed from your principle "prefer the option that gives higher values"; confirm or change.
- **[O]** Open: not answered yet. Must stay configurable or be decided during design.

---

## 1. Background
- Colleges following Outcome-Based Education (OBE), for NBA and NAAC, must show how well students attain Course Outcomes (COs) and, through them, Program Outcomes (POs) and Program Specific Outcomes (PSOs).
- The work is done today in Excel by faculty, then consolidated by coordinators and signed by faculty, HOD and director.
- The reference college is Vasavi College of Engineering (Autonomous), Hyderabad, CSE and CSE-AIML. Its mentor supplied: a course workbook (Deep Learning, 67 students), a CO-PO analysis report, an Action Taken Report, and a department/batch workbook (2021-25).
- Each college has its own method. This product must serve any college.

## 2. Problem
- Attainment calculation is manual, error-prone and hard to audit across sections, courses, departments and batches.
- Problems seen directly in the mentor's workbook:
  - attained levels are typed by hand, not calculated
  - student counts such as `/67`, `/66` and `61` are typed into formulas
  - the boundary is `>` in one sheet and `>=` in the others
  - SEE marks use a script number, not a roll number
  - course codes contain typos (`UI21` vs `UII21`)
  - manual overrides sit in an "updation" sheet with no reason or approver
  - the indirect value is a typed 3
  - values are pasted between workbooks with no link back to the marks
- No free, simple tool exists that a college can configure to its own method without code or vendor help.
- Rosters differ by college and section (different roll-number ranges and gaps from dropouts).

## 3. Goal
A simple, free web application where a college configures its method once, the configuration is saved and reused, and after marks are available everything else is automatic: section, course, department and batch results for COs, POs and PSOs, with reports and a full explanation of every number.

## 4. Objectives
1. Automate attainment calculation; derive every level by rule, never by typing.
2. Be configurable for any college, without code changes.
3. Reproduce the reference college's results exactly (within the rules in section 7).
4. Be explainable: any value can be traced to marks, students, mappings and rules.
5. Be reproducible: past, signed results stay interpretable after later changes.
6. Handle real rosters: any roll-number scheme, gaps, dropouts, section changes.
7. Be simple enough for lecturers to use without training.
8. Serve many colleges safely, with separate data.
9. Cost nothing to build and use.
10. Stay independent of any ERP, and keep later integration possible.
11. Support the college's quality process: gap analysis, action plans, action-taken reports, approvals.

## 5. Scope

### 5.1 In scope (first release)
- Academic structure, students, enrolments, faculty and assignments.
- Outcomes (COs, POs, PSOs) and CO-PO/PSO mapping.
- Assessments of different behaviours (section 7.3), marks entry and import.
- The full calculation chain: question, CO, course, section roll-up, department, batch.
- Course targets and their revision; PO/PSO targets.
- Direct attainment (complete). Indirect attainment: see 5.3.
- Reports and exports in the college's formats.
- Action plan and action-taken tracking.
- Roles, approvals, locking, audit trail and overrides with reasons.
- Validation against the mentor's workbooks and at least two other methods on paper.

### 5.2 Out of scope (initial)
- Replacing a college ERP; fees, payroll, library, hostel, transport.
- Live ERP/SIS/LMS integration (later phase).
- Online exams, automatic evaluation of answers, learning-content delivery.
- Guaranteeing any accreditation result.
- Users writing arbitrary code or unrestricted formulas.
- Paid AI services; native mobile apps.

### 5.3 Deferred / decide later
- **Indirect attainment** (surveys): you said "see later, once we get those workbooks". The design must leave a place for it: indirect CO from a student survey, indirect PO from recruiter, stakeholder and alumni surveys. Until real data exists, indirect is entered as a value (the reference workbook uses 3).
- Second reference method from the mentor ("don't keep any hope").

## 6. Users and roles
| Role | Needs |
|---|---|
| Platform administrator | Onboard colleges, platform-level support |
| College administrator | College settings, users, rosters |
| Department head (HOD) | Department results, review, sign-off |
| IQAC / accreditation coordinator | Methods, mappings, targets, reports |
| Programme / course coordinator | Course setup, assessment structure, course review |
| Lecturer | Enter and update marks for assigned courses and sections; write observations and action plans |
| Exam branch | Provides SEE marks (script-number based) per college policy |
| Students, recruiters, alumni, stakeholders | Give survey responses (when indirect is added) |
| Principal / director / management | Read results, sign reports |
| Auditor / reviewer | Read-only review of records, calculations and changes |
Not every college uses every role.

---

## 7. Business rules of the reference method (the core of the project)

### 7.1 Terms
- **Question** = one numbered question in an exam (it may have parts).
- **Assessment tool** = Internal-I, Internal-II, Quiz, Assignment, SEE (Semester End Exam), Lab sessional.
- **Attempted** = the student has a recorded mark for that question.
- **Level** = 1, 2 or 3 per the bands in 7.4.

### 7.2 Thresholds and boundaries
- **R1 [C]** The pass mark for a question is **60% of its maximum marks** (a configurable value).
- **R2 [D]** A student passes when marks are **greater than or equal to** the pass mark (the printed rubric says "at least"; `>=` gives the higher result). Boundary is configurable. The mentor's Internal-I sheet used `>`.
- **R3 [C]** Values are truncated to 2 decimals (rounding is a different setting).
- **R4 [D]** Truncation is applied to **final values only**; intermediate calculations keep full precision (this gives higher values, your stated principle). Configurable. *Tension:* a value near a target may display as, say, 2.19 and be treated as attained against 2.2 if comparison uses the unrounded value. The setting must say which value is compared. The batch workbook already shows totals unrounded in the file and rounded in its chart table.

### 7.3 Assessment tools and how each behaves
Each tool has its own behaviour. Behaviours must be definable per tool.

| Tool | Behaviour | Reference details |
|---|---|---|
| **Internal-I / II** | Question-wise | Per question: percent of students passing. Internal-I covers CO1 and CO2; Internal-II covers CO3 to CO5 (as an example). Choice questions possible (Internal-II has blanks). |
| **Quiz** | Per-student average | Average of 3 quizzes, max 5. Pass when the average is at least 3 (60%). Denominator: all students. **Absent counts as 0 in the average [C]**, so the average drops. Result level applies to **all COs**. |
| **Assignment** | Per-student average | Same as quiz (3 assignments, max 5). Applies to all COs. |
| **SEE** | Question-wise with choice | See 7.3.1. |
| **Lab** | Single total | Sessional total (30 marks) with 60% pass mark (18). One level used for every CO of the lab course. The workbook and the report disagree on lab details (sessional 30 vs sem-end 50). **[O]** |

**7.3.1 SEE rule (Vasavi; "only for my college") [C]**
- Q1 to Q10: compulsory, 2 marks each, tagged to COs in the paper.
- Q11 to Q17: 8 marks each, choice.
  - Q11 to Q16 have parts a and b (4 marks each). Q17 has parts a, b, c (4 marks each).
  - A question's marks = the sum of its parts. For **Q17 the best 2 parts count** (so Q17 is also out of 8).
  - Students write 5 of these 7 questions. The **best 5 question totals** (questions, not parts) are used.
  - Only the best 5 marks are entered. If a student attempted fewer than 5, the missing ones count as **0**. "Everything else is taken care of by the person entering."
  - **CO tagging:** Q11 to Q15 map to CO1 to CO5 in order. Q16a, Q16b map to CO1, CO2. Q17a, b, c map to CO3, CO4, CO5.
- **Open [O]:** since Q16 and Q17 contain parts of different COs, the CO of a question total is not defined. The mentor's workbook records marks by part (columns 11a to 17c with max 4 each and CO per part), which conflicts with "best 5 question totals". Also, "missing counts as 0" conflicts with the earlier answer "only students who attempted a question are counted per question". The design must support both denominators as a setting until this is settled.
- SEE denominator in the reference: students who attempted the SEE (66 of 67) [C].

### 7.4 From marks to levels
- **R5 [C]** For each question: `% passing = students passing / students counted` (see denominator rule).
- **R6 [C]** **Denominator:** per question, only students who attempted it count (SEE and choice questions). For quiz, assignment and lab the class strength is used. For the SEE, only students who attempted the SEE count.
- **R7 [C]** A CO's percentage for a tool = **plain average of the question percentages** for questions tagged to that CO (no weighting by marks).
- **R8 [C]** Level bands (percent of students passing):
  - Level 3: 60% or more
  - Level 2: 50% up to below 60%
  - Level 1: 10% up to below 50%
  - Below 10%: **no level; the system flags it [C]** ("flag it"). No Level 0.
  - Bands are configurable.
- **R9 [C]** When a CO is covered by both internals, the CO's internal level = **average of the two levels**.
- **R10 [C]** Levels are always computed automatically. A person with the right role may override a level, but a **reason is mandatory** and the override is recorded.

### 7.5 From levels to CO and course attainment
- **R11 [C]** Direct CO = `0.30 x Internal + 0.05 x Assignment + 0.05 x Quiz + 0.60 x SEE` (levels as inputs). Weights are the same for all departments, defined at university level. They are configurable.
- **R12 [C]** CO attainment = `0.8 x Direct + 0.2 x Indirect`.
- **R13 [C]** Course attainment = **simple average of its CO attainments** (courses with fewer than 5 COs average only the COs they have; blanks are not zero).
- **R14 [C]** Course status "Attained" when course attainment reaches the **course target** (at or above).
- **R15 [C]** **Targets are set per course.** The rule for revising them each year is **configurable [C]**. Candidate rules seen so far: (a) +0.5% of the current target when met, starting at 2 (your understanding); (b) +0.5 points when performance is better, unchanged when worse (the mentor's words); (c) x1.1 (pattern seen in the batch workbook). Not settled. **[O]**

### 7.6 Sections
- **R16 [C]** A course taught to several sections: all sections use the **same question paper**; the course result is the **average of the section results** (the stage at which averaging happens, level vs percentage vs final CO attainment, is **[O]**; default: average of section-level CO attainments).
- Section, course, department and batch results must all be available.

### 7.7 Course to PO/PSO
- **R17 [C]** CO-PO/PSO mapping uses values 1, 2, 3.
- **R18 [C]** Blank and 0 are different: blank means "not mapped"; 0 means "mapped with no strength". Treat them separately.
- **R19 [C]** Course PO_j = `sum(map_ij x CO_i) / sum(map_ij)` over the COs mapped to PO_j (verified against the report: PO1 2.29, PO2 2.28, PO3 2.41, PO4 2.38, PO5 2.31, PSO1 2.28).

### 7.8 Department and batch
- **R20 [C, as in the mentor's file]** Batch direct PO/PSO = simple average of the per-course values across all courses in all 8 semesters that have a value for it. Every course counts once; no credit weighting; each open-elective option counts as a course. Whether this is intended or a simplification is **[O]**.
- **R21 [C]** Batch total PO/PSO = `0.8 x Direct + 0.2 x Indirect` (indirect: see 5.3).
- **R22 [C]** PO/PSO targets exist at batch level (2.55 to 2.86 in the file). Whether they are program-level settings is **[O]**; default: yes.
- **R23 [C]** Reports compare the batch with earlier batches (2019-23, 2020-24, 2021-25) and count courses attained / not attained, split into core and non-core.
- **Which offering a batch uses** (backlog or detained students studying with another batch) is **[O]**.

### 7.9 Other rules
- **R24 [C]** Marks have distinct states: valid number (including zero), blank (not entered), absent, withheld, exempted, not applicable. Zero and blank are treated separately everywhere.
- **R25** Every result reports its denominator and exclusions.
- **R26** Small groups: show the count next to each percentage and warn when it is small (a design requirement, not in the mentor's files).
- **R27** Attempted-only denominators can inflate results; show the attempt rate beside each question's percentage.

---

## 8. Configurability requirements
The first release must let a college define, save and reuse (with versions) at least:
- **Pass mark:** percent of question max (default 60) and boundary (`>=` default, `>` possible).
- **Level bands:** the numbers, number of levels, the name of each level, what happens below the lowest band (flag).
- **Assessment tools:** which exist, their weights in Direct CO, and which behaviour each has (question-wise, per-student average, single total), plus the COs each covers or "all COs".
- **Aggregation:** plain average (default), per-section averaging, internals averaged per shared CO.
- **Choice rule:** "best N of M questions", parts-sum per question, "best K parts" within a question; what a missing choice counts as (0 or excluded).
- **Denominator rule:** attempted only, all enrolled, or SEE-attempted.
- **Direct/indirect split** (80/20 default), indirect source.
- **CO to PO/PSO** mapping values and the PO formula.
- **Roll-up:** how sections, departments, batches and courses combine, and what weights apply (equal by default).
- **Targets:** per course, per PO/PSO; revision rule.
- **Truncation / rounding:** mode, decimals, and which values are compared.
- **Absent handling** for quiz and assignment (absent = 0 default).
- **Overrides:** who can override, and that a reason is mandatory.
- **Scope of settings:** university-wide values (weights) shared by all departments, with room for department or course-level differences.
Saved configuration must be reused automatically and change only when an authorised user changes it. Changes are versioned. Results always show which version they used.

**What varies is both settings (numbers) and structure** (how an assessment behaves, how denominators work, how sections and courses combine). Both must be representable without code changes for the variations listed here. How is a design question.

---

## 9. Student identity and roster requirements
1. Roll numbers are only labels: not unique across colleges, batches or sections; not necessarily numeric or sequential; they can be alphanumeric and contain a college/year/branch pattern (for example `1602-23-748-001`).
2. Gaps are normal; never create students to fill gaps (the reference class has 67 students numbered between 001 and 306).
3. A student stays identifiable when the roll number or section changes.
4. Withdrawn students keep their history.
5. Not enrolled is different from enrolled with no mark.
6. Different SEE keys (script numbers) must be linked to students; the exam branch usually holds that link.
7. Students may also belong to a course offering with another batch (backlog); the batch roll-up needs a rule. [O]
8. Rosters differ by section and by college; imports must reconcile and report mismatches before data is accepted.

## 10. Data inputs and sources
| Data | Source | Notes |
|---|---|---|
| Rosters, sections | College admin / import | Any roll-number scheme |
| Internal, quiz, assignment, lab marks | Lecturer (entry or import) | Question-wise or totals |
| SEE marks | Exam branch / import | Keyed by script number; best-5 rule |
| CO-PO/PSO mapping, targets | Coordinator / IQAC | Per course; versioned |
| Surveys (indirect) | Students, recruiters, alumni | Deferred; see 5.3 |
| Observations, action plans, actions taken | Lecturer, HOD | Part of the mentor's reports |
Note: "only lecturers enter marks" holds for internals; SEE, surveys and setup data come from others.

## 11. Functional requirements
**Setup**
- F1 Manage colleges, departments, programmes, batches, semesters, courses, course offerings, sections, faculty, and users with roles.
- F2 Course identity must not depend on a typed code (typos, two codes for one course, twin courses in two departments).
- F3 Support one row/course with several options (open electives) and cross-department twin courses.
- F4 Define COs, POs, PSOs (and PEOs if used) with versions and effective periods; CO-PO/PSO mapping per course.
- F5 Define assessments, questions, parts, max marks, choice rules and CO tagging.

**Marks**
- F6 Lecturers enter and update marks only for their courses and sections; bulk entry and Excel/CSV import with validation and a preview.
- F7 Support all mark states in R24; distinguish blank from zero.
- F8 Validate (above max, wrong student, duplicate, unmatched), and keep the source of each import.
- F9 Keep change history (who, when, old and new value, reason).
- F10 Lock after approval; controlled reopening.

**Calculation**
- F11 Calculate automatically through every step in section 7; no typed levels or counts.
- F12 Show intermediate values, denominators and exclusions for any result.
- F13 Recalculate when marks, mappings or configuration change; keep earlier versions.
- F14 Mark results as provisional until required inputs are complete; flag below-lowest-band values and missing inputs.
- F15 Section, course, department and batch results; batch-to-batch comparison.
- F16 Targets: set per course; revise per the configured rule; PO/PSO targets; attained / not-attained status.

**Quality process**
- F17 Observations and action plans per course; link last year's plan to this year's action-taken report with dates and proof.
- F18 Gap view: COs/POs below target; question-wise weak points.
- F19 Approval and sign-off steps (faculty, HOD, director); signed results are frozen.
- F20 Overrides allowed only to authorised roles with a mandatory reason.

**Output**
- F21 Reports in the college's formats (see 12) and Excel exports; reports show college, batch, course, configuration version, data status.
- F22 Import of existing Excel data and a side-by-side comparison with the old workbook.

**Access**
- F23 Role-based access limited to assigned courses/departments; separation between colleges; full audit.

## 12. Required outputs (from the mentor's reports)
- Per assessment: CO attainment sheet (max marks, students at or above 60%, percentage, level) for assignments, quizzes, lab.
- Theory course CO attainment analysis: levels per tool per CO, direct, indirect, final, course attainment, target, status, observations, action plan, signatures.
- Lab course attainment analysis.
- CO to PO/PSO table (CO attainment, mapping, course-to-PO row).
- Action Taken Report with proof pages.
- Department/batch: CO attainment by course and semester; PO/PSO per course; batch direct, indirect, total; PO targets; three-batch comparison; attained/not-attained counts by core and non-core; list of corrections.
- A flat course list "for the NBA file".

## 13. Non-functional requirements
- **Cost:** no mandatory paid service, API or licence; any optional paid item must be labelled.
- **Usability:** simple; marks entry quick for a class-size list; clear row-level errors; guided setup for the configuring user.
- **Correctness:** matches the reference workbook; calculations testable on their own; no misleading results from incomplete data.
- **Reproducibility:** same data and configuration give the same results; history kept.
- **Explainability:** every number traceable.
- **Security and privacy:** access control; colleges separated; student data protected; India's DPDP Rules 2025 considered; clarity on who is responsible for data when other colleges' data is hosted; use anonymised data for development unless permission exists.
- **Scale:** many colleges, departments, batches and years. A single section is small (67 students), so the scale challenge is variety, not volume.
- **Availability and recovery:** official marks require backups and recovery that are defined and tested.
- **Maintainability:** rules documented; one college's change cannot affect another.
- **Portability:** works without an ERP; future data exchange possible.

## 14. Constraints and assumptions
**Constraints:** zero budget; limited student-project time; only one real method available; mentor access is slow; accreditation formats change.
**Assumptions:** the mentor's workbook is the reference for Vasavi's method; the same weights hold for all departments of the college; one question paper per course across sections; indirect data arrives later.

## 15. Acceptance scenarios
1. **Reference course (Deep Learning, 67 students)** produces the numbers in Appendix A.
2. **Reference batch (CSE 2021-25)** produces the numbers in Appendix B.
3. **Gaps and ranges:** a section numbered 1 to 4 and 6 to 8; Section A 1-100 and B 1-89; A 1-66 and B 67-130; alphanumeric ids.
4. **Same roll number in two sections** stays two students.
5. **Withdrawal / section change:** history kept; inclusion follows the configured rule.
6. **Blank vs zero vs absent:** each treated as configured; quiz absent counts 0.
7. **Boundary:** a student at exactly 60% passes by default; changing the boundary changes the result.
8. **Best 5 of 7 SEE questions** with parts and the Q17 best-2 rule; a student who attempted 4 gets a 0 for the fifth.
9. **Shared CO across two internals** averages the two levels.
10. **Quiz/assignment level applies to every CO.**
11. **Below 10%** is flagged, not given a level.
12. **Section roll-up:** two sections with the same paper average to the course result.
13. **Override:** needs role and reason, recorded, visible in reports.
14. **Configuration change:** later periods use the new version; earlier results keep the old one.
15. **Incomplete data:** result marked provisional.
16. **Second method on paper** (from a published college report) is expressed with the same settings without product changes.
17. **Saved configuration:** a new term uses it without redoing setup.
18. **Bad import:** errors are reported; valid unrelated rows not corrupted.
19. **Data isolation:** one college cannot see another's records.
20. **Freeze:** a signed report does not change when later marks change.

## 16. Definition of done
- **Domain:** the reference method is documented, reviewed and accepted by the mentor; open items in section 18 are decided or explicitly deferred.
- **Records:** all entities in F1 to F5 work; roster cases in section 9 pass.
- **Marks:** entry, import, states, validation, history and locking work.
- **Calculation:** outputs match Appendix A and B (using the agreed boundary and truncation settings); every rule in section 7 has test cases including edge cases (boundaries, truncation, choice rules, blanks, absentees, small groups).
- **Configurability:** every setting in section 8 can be changed without code; a second method (on paper) is expressed; configurations are versioned and saved.
- **Reports:** all outputs in section 12 can be produced and exported; they show configuration version and data status.
- **Quality process:** targets, action plans, action-taken reports, approvals and overrides with reasons work.
- **Security:** roles and separation between colleges tested; audit trail present.
- **Cost:** no mandatory paid dependency; demonstrated without paid hosting.
- **Documentation:** user guide, rules guide, known limits and unresolved items.

## 17. Success measures
- Time to produce a course result versus the Excel process.
- Zero mismatches against the reference workbooks for agreed cases.
- Lecturers enter a section's marks unaided.
- A second college's method can be set up by configuration only.
- No typed levels or counts remain in any output.

## 18. Open items (decisions still needed)
| # | Item | Default used for now |
|---|---|---|
| 1 | CO of Q16/Q17 totals (parts belong to different COs); part-level vs question-level storage | Support both; undecided |
| 2 | "Missing counts as 0" vs "attempted only" for SEE denominators | Both as a setting |
| 3 | Averaging of sections: at which stage | Average of section CO attainments |
| 4 | Target revision rule and starting value | Configurable; no default |
| 5 | Which value is compared with the target (truncated or unrounded) | Unrounded (higher) |
| 6 | Batch PO equal weight by design? Credits? | Equal weight |
| 7 | Which offering a batch uses (backlog / detained) | Undecided |
| 8 | Which students count for internals and lab (class strength vs SEE-attempted) | Class strength |
| 9 | Lab: 30-mark sessional or 50-mark SEE; indirect for labs | Sessional 30, one level for all COs |
| 10 | Who provides SEE marks and the script-to-roll mapping | Exam branch |
| 11 | CSE and CSE-AIML: shared COs and mapping, or separate | Shared definition, separate results |
| 12 | Are PO/PSO targets program-level settings | Yes |
| 13 | Indirect: survey questions, scale, mapping, response-rate rule, PO sources, weights | Deferred; entered value |
| 14 | Exact report formats and sign-off flow | As in section 12 |
| 15 | Whether action-plan tracking and approvals are in release 1 | Yes (in scope above) |
| 16 | Data for development and testing (real vs anonymised) | Anonymised |
| 17 | Second/third methods for paper validation | Published college reports |
| 18 | First target user group (engineering colleges only?) | Engineering (NBA) first |
| 19 | Level naming and number of levels in other colleges | Configurable |

## 19. Risks
| Risk | Consequence |
|---|---|
| Over-fitting to one college | The "any college" claim cannot be shown |
| Misreading the SEE rule (Q16/Q17, denominators) | Wrong CO levels |
| Truncation and boundary choices | Status flips near targets |
| Typed overrides and later edits | Unreliable history |
| Indirect data missing | Totals inflated by a typed 3 |
| Weak identity handling (roll numbers, script numbers, course codes) | Wrong students or courses |
| Config too complex | Lecturers stay on Excel |
| Student data of other colleges | Privacy and legal exposure |
| Free-tier limits | Interrupted service |
| Mentor availability | Open items stay open |
| Scope growth into an ERP | Core product late |

## 20. Decision log (answers received)
- Weights, bands and the method are the same for all departments (university level). [C]
- Level 1 is 10% to 50%; no Level 0; below 10% flagged. [C]
- Truncate to 2 decimals everywhere. [C]
- Internal-I: CO1, CO2; Internal-II: CO3, CO4, CO5; shared CO: average of levels. [C]
- SEE denominators per question: attempted only; best 5 question totals; Q11-Q17 structure as in 7.3.1. [C]
- Only SEE-attempted students count for the SEE. [C]
- Indirect CO: student survey; indirect PO: recruiter, stakeholder, alumni surveys; later. [C]
- Targets are per course; revision rule configurable. [C]
- Sections combine by averaging; all sections use one paper. [C]
- Course attainment is the plain average of COs; per-question average is plain. [C]
- Quiz/assignment: absent counts as 0. [C]
- "Attained" means reaching the target. [C]
- Blank and zero are separate. [C]
- Levels automatic; overrides need role and reason. [C]
- Below the lowest band is flagged. [C]
- When options differ, prefer the one giving higher values. [C]
- Second workbook: unlikely. Indirect workbooks: to come.

## 21. Glossary
OBE, CO, PO, PSO, PEO, CIE (internal), SEE (semester end exam), IQAC, NBA, NAAC, ERP: standard meanings.
- **Attempted:** a mark has been recorded for the question.
- **Attainment level:** 1 to 3 from the bands in 7.4.
- **Direct / indirect:** performance-based / survey-based.
- **Course offering:** a course given to a section in a term.
- **Batch:** the graduating cohort, for example 2021-25.
- **Methodology version:** a saved set of rules and values with an effective period.

---

## Appendix A: reference course expected values (Deep Learning, CSE-AIML, 2025-26, 67 students)

| | CO1 | CO2 | CO3 | CO4 | CO5 |
|---|---|---|---|---|---|
| Internal level | 3 | 3 | 3 | 3 | 3 |
| SEE level | 2 | 2 | 2 | 1 | 1 |
| Assignment level | 3 | 3 | 3 | 3 | 3 |
| Quiz level | 3 | 3 | 3 | 3 | 3 |
| Direct CO | 2.40 | 2.40 | 2.40 | 1.80 | 1.80 |
| Indirect CO (typed) | 3 | 3 | 3 | 3 | 3 |
| CO attainment | 2.52 | 2.52 | 2.52 | 2.04 | 2.04 |

- Course attainment: 2.328 shown as **2.32**; target 2.2; **Attained**.
- Per-course PO/PSO: PO1 2.29, PO2 2.28, PO3 2.41, PO4 2.38, PO5 2.31, PSO1 2.28, PSO2 2.32, PSO3 2.32.
- CO-PO map: CO1 (PO1 2, PO3 2, PO4 1, PSO1 1, PSO2 3, PSO3 3); CO2 (PO1 2, PO2 2, PO3 2, PO4 2, PO5 2, PSO1 1, PSO2 3, PSO3 3); CO3 (PO1 3, PO2 2, PO3 3, PO4 2, PO5 2, PSO1 2, PSO2 3, PSO3 3); CO4 (PO1 3, PO2 2, PO3 2, PO4 2, PO5 1, PSO1 2, PSO2 3, PSO3 3); CO5 (PO1 3, PO2 2, PO5 2, PSO1 2, PSO2 3, PSO3 3).
- Percentages in the workbook (with its own quirks: `>` in Internal-I, mixed denominators in SEE): Internal-I CO1 72.14, CO2 78.17; Internal-II CO3 79.89, CO4 86.86, CO5 69.50; SEE CO1 58.81, CO2 51.07, CO3 57.43, CO4 46.52, CO5 45.57. Quiz and assignment: 67 of 67 at 60% or more; lab: 67 of 67 at 18 or more marks.
- Test note: matching these percentages requires the workbook's own boundary and denominator quirks; with `>=` and consistent denominators some may change. Decide per case which result is the reference.
- Lab course: CO attainment 3 for all five COs; target 3; Attained.

## Appendix B: reference batch expected values (CSE 2021-25)
| | PO1 | PO2 | PO3 | PO4 | PO5 | PO6 | PO7 | PO8 | PO9 | PO10 | PO11 | PO12 | PSO1 | PSO2 | PSO3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Direct | 2.80 | 2.76 | 2.76 | 2.82 | 2.82 | 2.79 | 2.66 | 2.89 | 2.82 | 2.83 | 2.70 | 2.70 | 2.79 | 2.80 | 2.81 |
| Indirect (typed) | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Target | 2.55 | 2.65 | 2.55 | 2.55 | 2.65 | 2.75 | 2.65 | 2.86 | 2.86 | 2.86 | 2.75 | 2.65 | 2.55 | 2.55 | 2.55 |
| Total (file, unrounded) | 2.8399 | 2.8103 | 2.8118 | 2.8558 | 2.8555 | 2.8301 | 2.7248 | 2.9088 | 2.8594 | 2.8629 | 2.76 | 2.7598 | 2.8290 | 2.8384 | 2.8504 |

- Courses: CSE core 50 of 51 attained, non-core 29 of 29. CSE-AIML core 48 of 51 attained, non-core 28 of 29.
- Earlier batches for comparison (total): 2019-23 PO1 2.78, PO2 2.73, PO3 2.67 and so on; 2020-24 PO1 2.77, PO2 2.75, PO3 2.76 and so on (full table in the batch workbook).
- Total = 0.8 x Direct + 0.2 x Indirect; Direct = simple average of per-course values over all semesters.
- Known manual corrections in the file: Optimization Methods PO11 to 2.33; Semiconductor Physics PO10 to 0; Numerical Methods PO12 to 0; Human Values-II PO10/PO12 to 3; Human Values-II AIML CO attainment 1.4 to 2.

## Appendix C: known quirks in the reference files (do not copy blindly)
1. Levels are typed numbers.
2. Class strength typed into formulas (`/67`, `/66`, `61`).
3. Internal-I uses `>`; other sheets use `>=`; labels say `>`.
4. SEE mixes denominators (all 66 for Q1 to Q10; attempted for later questions).
5. Level 1 floor printed as 10% in one place and 20% in others.
6. SEE sheet has script numbers, not roll numbers.
7. Lab described as 30-mark sessional in the workbook and 50-mark SEE in the report.
8. Indirect values typed as 3.
9. Report dates (8.9.2026) fall after the academic year 2025-26.
10. Faculty name spelled two ways (Kour / Kaur).
11. Course codes: `UI21` vs `UII21`; typos on some rows; two courses in one row; open-elective header rows.
12. Course PO values and CO values are pasted, not linked.
13. Batch total unrounded in the file but rounded in the chart table.
14. Manual overrides in the "updation" sheet with no reasons.
15. Internal-II has 281 blank cells (blank = not attempted); Internal-I has none.
