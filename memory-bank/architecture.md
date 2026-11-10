# Architecture

Planned layout (from `docs/solution-design.md` section 17). Check which parts exist before relying on them.

```
config/            Django settings (base, dev, prod), urls, wsgi
apps/<module>/     models.py services.py views.py forms.py templates/ tests/
engine/            pure Python, no Django imports
  model.py         input/output data classes
  steps/           one file per step type
  pipeline.py      builds and runs the step graph
  precision.py     Decimal helpers (round, truncate)
  trace.py         explanation of every number
  schema.py        Pydantic method schema
  tests/ golden/   anonymised fixtures from the mentor workbooks
templates/ static/ docker/ scripts/ docs/
```

## Modules (apps/)
| Module | Owns |
|---|---|
| tenancy | college, RLS, per-request college setting |
| accounts | users, roles, login |
| academics | programmes, departments, batches, sections, courses, offerings |
| roster | students, roll numbers, enrolment, dropouts |
| outcomes | COs, POs, PSOs, CO-PO maps |
| assessments | assessment tools, question parts, choice groups |
| marks | mark grid, MarkCell states, paste/import entry |
| methodology | versioned method JSON, publishing |
| results | calculation runs, results, overrides, signed runs |
| quality | data checks, below-10% review, missing data |
| reports | PDF/Excel reports, charts |
| imports | mark-sheet and roster import parsing |
| audit | append-only, hash-chained log |
| integration | later: REST API, connectors |

Rule: modules call each other only through `services.py`; never import another module's models directly.

## Calculation flow
1. A service builds an immutable input snapshot (marks per part, roster, choice groups, outcomes map, method version).
2. `engine` runs the method's steps: question pass, denominator, choice select, bands, merge tools, weighted combine, roll up, map to outcomes, precision, target check.
3. The engine returns results plus a trace; nothing is written by the engine.
4. `results` stores the run (method version, engine version, snapshot hash). Approval flows (section, offering, batch) freeze it; a signed run is never altered.

## Data rules
- Every tenant table has `college_id`; PostgreSQL RLS filters it.
- Marks are per question part; states: value, blank, absent, withheld, exempted, not_applicable, not_attempted.
