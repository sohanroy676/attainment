# ADR-0007: Free demo hosting; colleges self-host real data

## Status
Accepted

## Date
2026-11-10

## Context
Budget is zero. Real student data is personal data (DPDP Rules 2025: main duties from 14 May 2027; under-18 consent unconfirmed).

## Decision
- Demo: Render free web service + Neon free PostgreSQL, anonymised data only, nightly encrypted `pg_dump`. Free-tier facts checked 2026-11-06; re-check before deploying.
- Real use: the college runs the Docker image on its own machine with local encrypted backups.
- No paid services anywhere; the app must work offline.

## Alternatives considered
- Render free Postgres: deleted after 30 days.
- Supabase free: pauses when idle.
- Central hosted service for all colleges: cost and data-protection duties fall on this project.

## Consequences
- The demo may sleep or be slow.
- Self-hosting needs a simple install and update guide (v0.11.0).
