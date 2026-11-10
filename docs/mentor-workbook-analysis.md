# Mentor's files: extracted attainment method (Deep Learning + DL Lab, CSE-AIML, 2025-26)

College: Vasavi College of Engineering (Autonomous). Faculty: Dr. S. Komal Kour. 67 students. Research only: no design or tech stack.
Files read: the marks workbook (5 sheets), the CO-PO attainment analysis report (docx), and the Action Taken Report (docx).
I checked the numbers by recomputing them, so the formulas below match her outputs.

---

## 1. What the files contain

| File | Contents |
|---|---|
| Marks workbook (xlsx) | Internal-I marks, Internal-II marks, Quiz/Assignment marks, Lab sessional marks, and Sem-End Exam (SEE) marks, each with its own attainment calculation at the bottom |
| CO-PO analysis report (docx) | Per-assessment attainment sheets, CO attainment analysis for the theory course and the lab, CO-to-PO/PSO tables, attainment rubric, observations and action plan |
| Action Taken Report (docx) | Last year's action plan, the action taken this year (with dates), and proof pages, per course |

## 2. Her method, step by step (theory course)

**Step 1: per-question threshold.** Every question has a max mark. The "60% of marks" row is `0.6 x max`. A student "passes" a question if their mark is at or above that value.
- So the 60% is applied **per question**, not per CO and not on a student's total.

**Step 2: per-question % of students.** `% = students passing the question / students (attempted)`.

**Step 3: question to CO.** Each question is tagged to one CO (a row labelled "CO" above the questions). A CO's value is the **simple average of the question-level percentages** for the questions tagged to that CO. It is not marks-weighted.

**Step 4: percentage to level (the rubric printed in the docs).**
- Level 3: at least 60% of students scoring at least 60% of marks
- Level 2: 50% up to below 60%
- Level 1: 20% up to below 50% (some sheets print 10% instead of 20%)
- Below that bar: not defined in the rubric (implicitly 0)

**Step 5: each assessment gives a level per CO** (sheet by sheet):
- **Internal-I** covers only CO1 and CO2. **Internal-II** covers CO3, CO4 and CO5. Together they give "Internal Exams" for every CO.
- **Quiz** and **Assignment**: each student's average of 3 quizzes (and 3 assignments), out of 5. A student passes with an average of at least 3 (60%). The resulting level is applied to **all COs**.
- **SEE**: 25 sub-questions across COs 1 to 5, same method (per-question %, average per CO, level).

**Step 6: direct CO attainment** (weights printed in the report):
`Direct = 0.30 x Internal + 0.05 x Assignment + 0.05 x Quiz + 0.60 x SEE`
- So the "internal" side is 40% (30 + 5 + 5) and SEE is 60%.

**Step 7: final CO attainment.** `CO = 0.8 x Direct + 0.2 x Indirect`. Indirect is 3 for every CO.

**Step 8: course attainment** = average of the 5 CO attainments. Compared with a set target (2.2): "Attained" or not.

**Step 9: CO to PO/PSO.** Each CO has a 0 to 3 mapping to each PO and PSO. For each PO or PSO:
`PO_j = sum(map_ij x CO_i) / sum(map_ij)` over the COs mapped to it. I recomputed PO1, PO2, PO3, PO4, PO5 and PSO1; all match her report.

**Step 10: narrative.** Observations on weak topics, action plan, and next year an Action Taken Report with dates and proof.

**Lab course:** a single sessional total (out of 30). A student passes with at least 18 (60%). The level (3) is used for the whole lab course, and the lab's CO attainment is that same level for every CO. No weights and no indirect part.

### Worked check (from her numbers)
- CO1: internal 3, SEE 2, assignment 3, quiz 3 gives 0.9 + 0.15 + 0.15 + 1.2 = 2.40.
- CO4: internal 3, SEE 1, assignment 3, quiz 3 gives 0.9 + 0.15 + 0.15 + 0.6 = 1.80.
- CO1 final = 0.8 x 2.40 + 0.2 x 3 = 2.52. CO4 final = 0.8 x 1.80 + 0.6 = 2.04.
- Course attainment = (2.52 x 3 + 2.04 x 2) / 5 = 2.328, which she shows as **2.32**.
- PO1 = (2x2.52 + 2x2.52 + 3x2.52 + 3x2.04 + 3x2.04) / 13 = 2.2985, which she shows as **2.29**.

## 3. How this differs from the generic model I gave earlier

- I described a student-level test ("student attains the CO if at least 60% of the CO's marks"). Her method is **question-level**: the 60% is per question, and the CO percentage is the average across questions. The product must support this method, and ideally my student-level method too, as a configuration choice.
- Levels are not purely "percentage of students"; every level comes from the same rubric but is applied separately to each assessment tool.
- Quiz and assignment results apply to all COs; internals map each exam to only some COs; the lab gives one level for everything.
- She **truncates, not rounds**, to two decimals (2.328 shows as 2.32; 2.2985 shows as 2.29). Rounding rules matter for matching her output.

## 4. Problems and inconsistencies found (these matter for the product)

1. **Hardcoded levels:** the attained levels (3, 3, 2, 2, 1...) are typed numbers, not formulas. Only the percentages are calculated.
2. **Hardcoded denominators:** `/67` and `/66` are typed into formulas; Internal-II has the number of students who attempted Q1 typed as 61.
3. **`>` versus `>=`:** Internal-I counts marks strictly greater than 60%; Internal-II and SEE count at or above it. Rubrics say "at least". The boundary rule differs between sheets.
4. **Label mismatch:** rows say "scoring > 60%" while formulas use `>=`.
5. **Different denominators for different questions** within one sheet: the first ten SEE questions divide by all students (66), later questions divide by those who attempted (e.g. 50). Choice questions and blanks change who is counted.
6. **Blank vs zero:** a blank cell means "not attempted" (281 blank cells in Internal-II) and is excluded from the count; a zero counts as an attempt. The sheet depends on people leaving cells blank.
7. **Class size differs:** 67 students in internals, quiz, assignment and lab; 66 in the SEE sheet (absent or detained student; not recorded).
8. **SEE has no roll numbers:** it uses a "Script Number" and serial number only, so SEE marks cannot be joined to students without a separate mapping.
9. **Roll numbers have gaps:** format `1602-23-748-NNN`; 67 students numbered between 001 and 306 (for example 018, 024 and 042 are missing, and the list jumps after 064). This confirms the roll-number requirements. The same list appears in the same order in four sheets.
10. **Rubric lower bound differs:** Level 1 starts at 10% in the report and 20% in the sheets.
11. **Lab described two ways:** the report says "Sem-End Exam (Grade), max 50"; the workbook has "Sessional Marks, total 30M". They are different assessments.
12. **Indirect attainment:** always 3, with no survey data or calculation in these files.
13. **Faculty name** spelled differently across documents (Kour vs Kaur): free-text fields are not controlled.
14. **Internal exam levels:** the report shows 3 for all COs, but the workbook has only CO1 and CO2 for Internal-I and CO3 to CO5 for Internal-II. The combination logic is not visible in the workbook.
15. **Target of 2.2** is typed per course; there are no CO-level or PO-level targets here.
16. **Dates:** reports are dated 8.9.2026 while the academic year is 2025-26 (check whether this is a typing slip).

## 5. What the files reveal about requirements

- **Configurable pieces confirmed:** per-question threshold (60%), level bands, assessment weights (30/5/5/60), direct/indirect split (80/20), CO-PO mapping 0-3, course target, truncation to 2 decimals.
- **Several assessment types behave differently:** question-wise (internals, SEE), student-average (quiz, assignment), single total (lab).
- **An assessment can cover only some COs** (Internal-I: CO1 and CO2).
- **Applying one level to all COs** (quiz, assignment, lab) must be possible.
- **Per-question denominator choice** (all students vs those who attempted) must be configurable.
- **Reports beyond numbers:** observations, action plan, the previous year's actions and the actions taken with dates/proof, signatures (faculty, HOD, director).
- **Section / course / department / batch:** these files show one section (AIML) of one course. Nothing here shows how sections, departments or batches are combined; this still needs the mentor.
- **Roll-up beyond the course** (department and batch PO attainment) is not shown at all.

## 6. Open questions for the mentor
1. Why are the levels typed manually: is it a rule (for example judgement) or just convenience?
2. Should the boundary be `>=` or `>` (the sheets differ)? What is Level 0, and is the Level 1 floor 10% or 20%?
3. Why truncate and not round the final values?
4. How do internal-exam levels from Internal-I and Internal-II combine into one level per CO (average, best, other)?
5. Is the SEE per-question denominator meant to differ (all students vs attempted)?
6. Where do the indirect value (3) and the survey data come from?
7. How are lab course COs scored when the lab has a single total?
8. How are department-level and batch-level PO attainment calculated from course results?
9. How are absent, detained or withdrawn students treated (67 vs 66)?
10. Are the weights 30/5/5/60 and the 80/20 split university-wide or chosen per course?
11. Where is the target (2.2 for theory, 3 for lab) decided, and are there PO-level targets?
12. Can she share a second course's workbook (or another faculty's) to see how much the method varies?

## 7. Proposed test cases from these files
- Recompute each question-level percentage, CO average and level; they must match the sheet.
- Recompute Direct, final CO, course attainment (2.328 shown as 2.32 with truncation) and PO1 to PO5 and PSO1 to PSO3.
- Edge case: the blank (not attempted) versus zero distinction in Internal-II.
- Edge case: the `>` versus `>=` difference in Internal-I.
- Edge case: roll-number gaps and SEE data keyed by script number.
- Lab: 67 students at 18 marks or more gives 100% and Level 3.

---

## 8. Answers received (2026-11-06) and what they settle

| # | Answer | Effect on the method |
|---|---|---|
| Boundaries | Level 1 is 10% to 50%; there is no Level 0 | Level bands: L3 at 60% or more, L2 50 to under 60, L1 10 to under 50. Below 10% is not defined (open) |
| Rounding | Truncate to 2 decimals everywhere | Confirmed as the rule for all values |
| Internals to COs | Internal-I covers CO1 and CO2; Internal-II covers CO3, CO4, CO5; where a CO appears in both, take the average | Internal level per CO = average when both exams cover it |
| SEE denominator | Per question, only students who attempted count. Students answer 5 of the choice questions (Q11 to Q17), so take the top 5 | Only SEE has choice; denominators are per question |
| Indirect | Indirect CO comes from a student survey; indirect PO comes from recruiter and stakeholder surveys | Indirect PO is a separate input at programme level |
| Absent/detained | Only students who attempted the SEE count | Class strength for SEE = SEE attempted |
| Weights | Same for all departments; set at university level | Weights and bands are defined once for the university, not per department |
| Targets | Per course, revised each year by +0.5 if the course did better; kept the same if it did worse | Target is versioned per course per year |
| Second workbook | She will try, no promises | Plan with one reference method only |

### Still open / unclear
1. **Typed levels:** question 1 (why levels are typed by hand) was not answered. Assumption: they should be derived by rule.
2. **Lab:** how a lab course is scored was not answered. Assumption: single total, 60% bar, one level for all COs.
3. **"Top 5 marks":** does it mean, for each student, the best 5 of the questions they attempted among Q11 to Q17? Or the first 5 attempted? How are ties and extra answers handled?
4. **"Unit 3 in both":** does this mean CO3 is covered by both internals? (Internal-I in the file covers only CO1 and CO2.)
5. **Target step:** "+0.5%" - is it +0.5 on the 0 to 3 scale (for example 2.2 to 2.7) or +0.5 percent? "Performed better" means attainment above target, or above last year's attainment?
6. **Below 10%:** with no Level 0, what level applies under 10%?
7. **Department/batch roll-up and the "attached workbook":** you mentioned an attached workbook for the roll-up question, but no new file reached me. Please re-send it.
8. **Indirect PO:** how survey results turn into a PO value, and how it combines with direct PO (80/20 as for COs?).
9. **Rounding vs truncation of the percentages** that feed the levels (for example 59.99% shown as 59.9 or 60).

---

## 9. Follow-up answers (2026-11-06, later) and the batch-level workbook

### 9.1 Answers received
- **Top 5 for SEE:** if a student attempted 7 choice questions with marks 4, 3, 4, 4, 2, 4, 4, only their best 5 count (here five questions of 4 marks). Applies per student, to Q11 to Q17 only.
- **Target revision (user's reading):** if the current target is met, next time's target = current target + 0.5% of itself; start from a target of 2. *Not confirmed with the mentor. See the observation below.*
- **Internals:** when a CO (for example a unit) is split across both internals (first half in Internal-I, second half in Internal-II), take the average of both internals' CO value.
- **Levels:** levels are 1 to 3; below 10% is not expected in practice. Should be configurable and automatic in the product.
- **Typed levels / lab scoring:** nothing was said. Treat as: levels should be derived automatically by rule.
- **Indirect workbooks:** the mentor will send them later.

### 9.2 What the new workbook is (CSE and CSE-AIML graduating batch 2021-25)
This is the **department / batch level**, one level above the course workbook. Sheets:
| Sheet | Purpose |
|---|---|
| CSE_CO_Attainment, AIML_CO_Attainment | Every course of all 8 semesters: course code, name, set target, course CO attainment, status (Attained or not), CO1 to CO5 attainment |
| For NBA File CO_Attainment | Same data as one flat list, for the NBA file |
| CSE_PO_Attainment, AIML_PO_Attainment | Per course, its PO1 to PO12 and PSO1 to PSO3 attainment; then the batch summary rows |
| temp 21-25 CSE | Working copy of the PO table with internal codes (C101...) |
| updation | List of manual overrides ("exist" vs "changed" values) |
| CSE, AIML | Course lists with numbers that link a CSE course to its AIML twin |
| CSE 3yrs Graph PO PSO attainment | Batch comparison 2019-23, 2020-24, 2021-25 against PO targets (feeds charts) |

### 9.3 Batch-level method (from the formulas)
1. **Course data is pasted in as values.** Each course's CO attainment (CO1 to CO5) and its per-course PO/PSO values are typed or pasted from the course workbooks. The only formulas are the batch averages and a few counts.
2. **Per-course PO/PSO** values have the same meaning as in the course workbook (CO attainment weighted by the CO-PO mapping). Blank means the course does not map to that PO.
3. **Batch direct PO** = simple average of the per-course values in that PO's column, over **all courses in all 8 semesters** that have a value. Every course counts equally (theory, lab, project, open elective all alike; no credit weighting).
   - Open electives: each open-elective option is its own row and counts as a course.
4. **Batch indirect PO:** typed as 3 for every PO and PSO (no survey data in the file).
5. **Total batch PO** = `0.8 x Direct + 0.2 x Indirect`, same split as at CO level.
6. **PO targets** are typed per PO (2.55 to 2.86) and compared to the total.
7. **Three-batch comparison** puts total and direct PO side by side for 2019-23, 2020-24 and 2021-25.
8. **Course status summary:** counts of courses attained and not attained, split into core and non-core courses. CSE: 50 of 51 core and 29 of 29 non-core attained; CSE-AIML: 48 of 51 core and 28 of 29 non-core.

### 9.4 New findings
- **The level above course:** department / batch results are built only from per-course results; so the product needs a reliable course-to-batch roll-up, not just course calculations.
- **Course-level targets vary a lot:** 23 different target values from 1.5 to 3 across 101 course rows (labs and projects mostly at 3). *Observation, unverified:* several targets look like 1.1 times another (2.2 to 2.42, 2.5 to 2.75, 2.42 to 2.66), which does not match "+0.5%". Please confirm the target rule with the mentor.
- **Same course, two departments:** CSE and CSE-AIML share courses under different codes (for example `UI21...` vs `UII21...`) and have their own results; the course lists are linked by hand through numbers in the "CSE" and "AIML" sheets. Codes contain typos (for example `UII21PC720CS` is used for NLP in a CSE sheet).
- **A row can hold two courses:** "NLP Lab / Advanced Databases Lab" shares one row and code field. Open-elective rows have a header row followed by sub-rows.
- **Batch results change after the fact:** the "updation" sheet lists manual corrections (for example Optimization Methods PO11 changed to 2.33, Semiconductor Physics PO10 changed to 0, Human Values-II PO10/PO12 changed to 3, and a CO attainment of 1.4 changed to 2 for AIML). Corrections after mapping or data changes need a trail.
- **Some courses have only 4 COs** (blank CO5); averages must ignore blanks, not treat them as 0.
- **Indirect PO uses 3 for all POs** until the real recruiter/stakeholder survey data arrives.
- **Core vs non-core** is a course attribute used in reporting.
- **No weights by credits** are used anywhere in the PO roll-up.
- **Batch naming:** "2021-25 Graduating Batch" ties results to the batch (cohort), not to the academic year of a single course.

### 9.5 New open questions
1. Is the target-revision rule +0.5% of the target (2.0 to 2.01), +0.5 points (2.0 to 2.5), or 10% as the file suggests? Is it applied only when the target was met, and from what starting value?
2. If the target was not met, is it kept the same or lowered?
3. Is the batch PO a simple average of courses (as in the file) by design, or would the mentor want credit weighting?
4. How are the per-course PO values produced (the exact CO-PO map)? That needs each course's CO-PO matrix; the course workbook gave one for Deep Learning.
5. How do the typed overrides in "updation" get decided and approved?
6. Do CSE and CSE-AIML share one course definition (same COs and mapping) with separate results, or separate definitions?
7. When the indirect workbooks arrive, which surveys feed which level (course exit survey for CO, graduate exit/recruiter/stakeholder for PO)?

### 9.6 Target scope (confirmed 2026-11-06)
- Target values are set **per course** (matches the "Set Target" column in the batch workbook).
- The workbook also has a separate target per PO / PSO at batch level (2.55 to 2.86). Not yet confirmed whether that stays a separate, program-level setting.
