# Testing Requirements

After implementing any feature or fix:

1. Check if tests already exist for the changed code.
2. If no tests exist, write tests covering:
    - The main expected behavior (happy path)
    - Edge cases (empty input, blank vs 0 vs absent, boundary values such as a mark exactly at the pass mark, gaps in roll numbers, large inputs)
    - Error/failure paths (invalid input, bad imports, forbidden roles, other college's data)
3. Write tests "as if trying to break the feature" — genuinely adversarial, not just re-confirming the code does what it does.
4. Run the FULL test suite (`uv run pytest`) to catch regressions.
5. If any test fails, debug and fix the root cause before proceeding. Never comment out or delete a failing test to make the suite pass.
6. Only after all tests pass, proceed to the commit workflow.

Framework, location and markers are defined in `memory-bank/tech-stack.md`: `engine/tests/` (unit, property, golden), `apps/<module>/tests/` (integration, isolation), `tests/e2e/` (Playwright). Markers: `unit`, `golden`, `property`, `integration`, `isolation`, `e2e`, `perf`, `ops`. Coverage target: 90% for `engine/`; 85% for `apps/tenancy/`, `apps/marks/`, `apps/results/`.

- Each version's tests are listed in `ROADMAP.md` (A-tests automatic, M-tests manual). Implement the A-tests for the version you build, and record M-test results in `docs/test-reports/` at release.
- Golden results (R1 to R4 in `ROADMAP.md`) are never edited to make a test pass. A change needs a written reason, per the roadmap's versioning rules.
- Fixtures contain anonymised data only.
- Run slow suites (browser, performance, large property runs) in the background and watch them with Monitor (see CLAUDE.md), not by polling.
