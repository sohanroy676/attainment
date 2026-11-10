# ADR-0005: Marks per question part, denominator by choice

## Status
Accepted

## Date
2026-11-10

## Context
In the mentor's workbooks, marks and CO tags are per part (11a, 11b, 17c). Some questions are choice questions (SEE: answer any 5 of Q11-17; Internal-II: any 4 of 6). Blank, zero and absent mean different things.

## Decision
- Store one MarkCell per student x part x attempt, with a state: value, blank, absent, withheld, exempted, not_applicable, not_attempted.
- Each question or choice group sets its denominator. `by_choice`: a choice question counts only students who attempted it; a compulsory question counts everyone who sat the assessment. Students absent for the whole assessment are excluded (user decision 2026-11-09).
- Missing data blocks by default (`MissingData`); it is never read as 0.

## Alternatives considered
- Marks per question: cannot reproduce part-level CO tagging.
- Blank as 0: silently lowers attainment.

## Consequences
- Larger mark tables and a more careful marks grid.
- The mark-sheet import must map columns to parts.
