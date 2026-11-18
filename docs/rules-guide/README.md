# Rules guide (first draft, for the mentor and IQAC to correct)

How the calculation works, in the order it runs, with the setting that controls each step.
A college changes these settings in its method (a JSON file of the `attainment-method/1` format);
nothing here needs a code change. Example: `docs/examples/method.json`. Try it:

```
uv run python -m engine run docs/examples/method.json docs/examples/sample-marks.json --trace
```

## The order of work
1. **Marks states.** A mark is one of: a number (0 is a real mark), *blank* (nothing entered, for
   example a question not chosen), *absent*, or *dropped* (answered but not counted, see step 3).
   These are never mixed up.
2. **Absent marks** (`absent`): `zero` counts an absence as 0; `exclude` or `skip` leaves the item
   out; `error` stops the run. Quiz and assignment use `zero` in the example method. A student
   absent for the whole assessment (`whole_assessment_absent`): `exclude` leaves them out of every
   denominator; `count_as_fail` keeps them in the denominator with no passes. Their marks, if any
   were typed, never count.
3. **Choice questions** (`choice`, per choice group): keep the best `best_n` questions per student,
   ranked by question total; a tie goes to the lower question number. `best_k_parts` keeps the best
   K parts of one question (for example 2 of 3 in Q17). A student who answered fewer than N loses
   nothing. Every dropped answer is written to the trace.
4. **Pass mark** (`pass_pct`, `boundary`): a part passes when the mark reaches the percentage of
   its maximum. `>=` passes a mark exactly at the line (1.8 of 3 at 60%); `>` does not. An approved
   per-part **override** (a pass mark and a mandatory reason) replaces the percentage for one part.
5. **Denominator** (`denominator`): `by_choice` (default) divides a choice question by the students
   who attempted it and a compulsory question by everyone who sat; `attempted`, `sat`, `enrolled`
   and `fixed` (`fixed_n`) are the alternatives. A denominator below `small_group_warning`
   (default 10) is flagged in the trace.
6. **CO percentage:** the mean of the percentages of the parts tagged to that CO.
7. **Quiz and assignment** (`per_student_average`): each student's items are averaged and pass at
   `pass_pct` of `max`; the class percentage applies to the COs in `applies_to`. **Lab**
   (`single_total`): the total passes at `pass_mark` (or `pass_pct`).
8. **Levels** (`levels.bands`): the unrounded percentage picks the band. Below the lowest band the
   result is flagged and `value_for_calc` says what later steps use: `block` (stop for review, the
   run is provisional), `zero`, or a number.
9. **Merging tools** (`merge`): Internal-I and Internal-II are averaged where both cover a CO; a CO
   covered by one is that one's level. Levels may be fractional (3 and 2 give 2.5).
10. **Direct attainment** (`direct`): sum of weight × level. Weights must sum to 1.
    If a tool gives nothing for a CO, `missing_data` decides: `block` (default), `renormalise`
    (the other weights are scaled up to 1) or `zero`.
11. **Final CO** (`final`): 0.8 × direct + 0.2 × indirect. Indirect is a value entered per CO until
    surveys exist; with no value entered the CO is stopped for review. Direct-only is always shown.
12. **Course attainment:** the mean of the final CO values that have one; compared with the target
    using the unrounded value (`precision.compare_with`: `unrounded` or `displayed`).

## From the course to the batch (engine 0.3.0)
13. **Sections** (`rollup`): an offering with several sections is calculated section by section and
    rolled up at one stage. `attainment` (default) takes the mean of the sections' final CO values;
    `level` rolls the tool levels, `pct` rolls the tool percentages and then applies the bands.
    `method`: `mean`, or `weighted_by_students` (weights = enrolled students per section). A
    section that is stopped for review blocks the course; every section stays visible.
    Try: `uv run python -m engine run docs/examples/method-offering.json docs/examples/sample-offering.json`
14. **Outcomes** (`po`): each PO and PSO is the weighted mean of the final CO values mapped to it:
    sum(strength x CO) / sum(strength). A CO that is not mapped is left out; a strength of 0 adds
    nothing. If every usable strength is 0 the outcome is blank (default `all_zero: blank`) or 0.
    A CO with no value is skipped; a CO stopped for review blocks the outcome.
15. **Targets** (`targets`): the course is compared with its target using the unrounded value
    (or the displayed one, see Rounding). A result within `near_target_margin` (default 0.01) of
    the target gets a warning flag either way. A target revision rule (`revise`) is a small table:
    `manual` (default, never changes it), `add_points`, `add_percent`, `multiply`; `if_not_met`
    is `keep` or `lower`; `floor` and `ceiling` hold the result. The revision is offered as a
    calculation; whether the college applies it automatically is still open.
16. **Batch:** for each outcome the direct value is the simple average of the course values (a
    blank course is skipped, a 0 counts), the total is `batch.direct` x direct + `batch.indirect`
    x entered indirect (0.8 and 0.2 by default), compared with the outcome's target. Courses
    attained and not attained are counted per category (core, non-core).
    Try: `uv run python -m engine batch docs/examples/method.json docs/examples/sample-batch.json`
17. **Other ways to get a CO percentage** (`aggregate`, per question-wise tool): the default is the
    plain mean of the part percentages; `marks_weighted` weights each part by its maximum mark;
    `student_level` counts a student as passing the CO when their marks on the CO's answered parts
    reach `student_level_pct` of the maximum of those parts. `docs/examples/method-college-b.json`
    is a complete second method (different bands, weights, `>` boundary, rounding) written as
    configuration only.

## Rounding
Arithmetic keeps 40 digits; nothing is rounded between steps. Values are rounded only for display,
by `precision`, which can differ per level (`question_pct`, `co`, `course`, `po`, `batch`; any level
without its own rule uses `default`): `truncate` (default), `round` (half away from zero, like
Excel) or `none` (all digits), with `places`. `compare_with` says whether a target is compared with
the unrounded value (default) or the displayed one: in the CSE 2021-25 batch PO9 is 2.8594 against a
target of 2.86, so it is Not attained unrounded and Attained if the total is rounded to 2.86 first.
Floating-point numbers are never used: 0.8 × 2.4 + 0.6 gives 2.52 exactly (a float gives 2.5199…
and truncates to 2.51).

## What the run records
Every run returns a trace (each step: inputs, rule, counts, denominator, exclusions, result), the
engine version, a hash of the input and a hash of the output. The same input always gives the same
hashes.

## Questions for the mentor (please answer or correct)
- Is Internal-II "answer any 4 of 6" (check against the paper)?
- Which result is official for Deep Learning: 2.18 (strict 60%) or 2.32 (typed pass marks)?
- When no value exists for a CO from one tool, should the default stay "stop for review"?
- Is the merge of the two internals always a plain average?
- Should the batch status compare the unrounded total (PO9 Not attained) or the rounded one?
- Should a target revision rule apply automatically each year, or stay manual?
- Which other colleges' published methods can we use to test that the rules are general enough?
