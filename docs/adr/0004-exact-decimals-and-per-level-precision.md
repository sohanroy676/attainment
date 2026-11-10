# ADR-0004: Exact decimals and per-level precision

## Status
Accepted

## Date
2026-11-10

## Context
The reference workbooks round at several levels. With floats the reference CO1 is 2.5199999999999996, which truncates to 2.51 instead of 2.52. Python's default rounding is half-even (2.845 gives 2.84); Excel gives 2.85.

## Decision
- The engine uses `Decimal` only; the database uses `numeric`. Floats are banned in `engine/`.
- Precision is configured per level (round or truncate, digits) and the rounding mode is always set explicitly (half-up).
- The value used for comparison with a target is separate from the displayed value; default is unrounded (user decision 2026-11-09).

## Alternatives considered
- Floats with tolerance: wrong answers at boundaries.
- Rounding only at the end: does not reproduce the mentor's files.

## Consequences
- Slightly slower arithmetic (irrelevant at this size).
- Golden tests can compare exact values.
