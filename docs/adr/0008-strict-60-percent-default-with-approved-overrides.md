# ADR-0008: Strict 60% pass rule by default; per-part overrides need a reason

## Status
Accepted (the college's final choice between the two reference results is still open)

## Date
2026-11-10

## Context
The Deep Learning workbook reproduces its report (course 2.32, Attained) only when Internal-II pass marks are typed values (2 for 3.5-mark parts, 57%). With a strict 60% rule the course is 2.18 (Not attained, target 2.2).

## Decision
- Default: strict 60% of the maximum mark per question part.
- A per-part pass-mark override is allowed with a reason, before approval only; it is audited and shown in the trace.
- Both results are kept as references: R1 (strict, 2.18) and R2 (overrides, 2.32). Golden tests cover both.

## Alternatives considered
- Copy the typed values as the rule: hides an inconsistency in the source files.
- No overrides: cannot reproduce what the college already published.

## Consequences
- The college must decide which result is official before the pilot (open item).
- Overrides are visible in reports so reviewers see when a result depends on one.
