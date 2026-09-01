# Challenge release cadence

MakeItGreen publishes one reviewed challenge per week. Quality gates matter
more than the calendar; an unfinished challenge rolls forward rather than
shipping with ambiguous tests.

## Weekly cycle

| Day | Deliverable |
|---|---|
| Monday | Choose one interview behavior and write its observable contract. |
| Tuesday | Build the smallest realistic broken repository and evidence. |
| Wednesday | Write deterministic tests and confirm the pristine repo exits 1. |
| Thursday | Implement and review the solution; confirm the overlay exits 0. |
| Friday | Edit the brief, add talking points, run full validation, and publish. |

## Release gates

A challenge is catalog-ready only when:

- the failure represents a plausible production or interview mistake;
- at least one unrelated behavior already passes in the pristine repo;
- tests use injected clocks, barriers, or fakes instead of sleeps and networks;
- `tests/` and evidence folders are read-only;
- the solution fixes causes rather than weakening assertions;
- `SOLUTION.md` explains root cause, repair, and interview tradeoffs;
- `python scripts/validate_challenges.py` passes for the full catalog.

## Four-week rotation

Rotate the primary skill so catalog growth stays balanced:

1. repository or API contract;
2. concurrency or database correctness;
3. incident or runtime diagnostics;
4. architecture extension or a deliberate multi-bug exercise.

Quarterly, review completion data and retire near-duplicate ideas. A second
language release begins only after its runtime contract has the same isolation,
timeout, result parsing, and pristine/solution validation guarantees as Python.
