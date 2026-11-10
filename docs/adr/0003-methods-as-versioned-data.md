# ADR-0003: Attainment methods are versioned data

## Status
Accepted

## Date
2026-11-10

## Context
Every college has its own thresholds, weights, levels and rounding. The project must work for any college without per-college code.

## Decision
- A method is JSON, validated by Pydantic, built from a fixed catalogue of steps (QuestionPass, Denominator, ChoiceSelect, Bands, MergeTools, WeightedCombine, RollUp, MapToOutcomes, Precision, TargetRevise, ...).
- No free-text formulas and no code in config.
- A published method version is immutable; changes make a new version. Each calculation run records the method version and engine version.

## Alternatives considered
- Per-college code branches: does not scale, cannot be audited.
- A formula language or spreadsheet engine: hard to validate, easy to get wrong silently.

## Consequences
- New kinds of rule need a new catalogue step (a code change), not just config.
- Old runs stay reproducible; old method versions must keep loading.
