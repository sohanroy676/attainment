# ADR-0001: Record architecture decisions

## Status
Accepted

## Date
2026-11-10

## Context
Early decisions (stack, hosting, calculation rules) get forgotten or re-argued, especially across AI-agent sessions that keep no memory between chats.

## Decision
Use lightweight ADRs for significant, hard-to-reverse decisions. One file per decision in `docs/adr/`, from `adr-template.md`. Skip ADRs for small, reversible choices.

## Alternatives considered
- Rely on git history and memory: the "why" is too easy to lose.
- Full design doc per decision: too heavy for a small team.

## Consequences
A little more writing per major decision; decisions stay traceable. The full design (`solution-design.md` v1.2) is the source for ADRs 0002 to 0008.
