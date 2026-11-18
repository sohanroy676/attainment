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

## Rounding
Arithmetic keeps 40 digits; nothing is rounded between steps. Values are rounded only for display,
by `precision`: `truncate` (default) or `round` (half away from zero, like Excel), with `places`.
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
- Not yet built (v0.3.0): sections roll-up, PO/PSO mapping, batch roll-up, target revision.
