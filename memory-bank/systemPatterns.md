# System patterns

- **Pure engine:** `engine/` takes data and returns data. No Django, no I/O, no clock, no randomness.
- **Config as data:** method = versioned JSON validated by Pydantic, using a fixed catalogue of steps. New rule kind = new step + tests, not a formula string.
- **Decimal everywhere:** `Decimal` and `numeric`; rounding mode always explicit; display precision separate from compared value.
- **Computed, not typed:** levels, counts and attainment are always calculated. Changes happen only through override records with a reason, before approval.
- **Immutability:** published method versions and signed runs are never edited; changes create a new version or run.
- **Trace:** every result carries the steps and inputs that produced it; reports show it.
- **Blocking checks:** `MissingData` defaults to block; below 10% stops for review. Nothing is silently treated as 0.
- **Services boundary:** modules talk through `services.py`; views and forms stay thin.
- **Tenancy:** `college_id` on every tenant table, RLS via `SET LOCAL` per request transaction; the isolation suite discovers models automatically.
- **Audit:** append-only, hash-chained log; writes go through the audit service.
- **Goldens:** fixtures from the mentor workbooks (anonymised); expected values in `ROADMAP.md` section 3. Never edit a golden to make a test pass; a change needs a written reason and a MINOR bump.
- **UI:** server-rendered Django templates + HTMX; JavaScript only for the marks grid and charts. Works offline (no CDN at runtime).
