# MakeItGreen challenge authoring standard

This document defines the minimum quality bar for every MakeItGreen challenge,
including the candidate question, starter repository, tests, reference fix, and
solution walkthrough.

The goal is not to maximize test counts or solution size. The goal is to create a
small, realistic repository that reveals how a candidate reads unfamiliar code,
reconstructs a behavioral contract, finds interacting defects, and explains a
production-quality repair.

## 1. Core principle

A challenge is measured by **independent engineering decisions**, not by the number
of test cases.

A parameterized test may exercise useful boundary conditions, but ten parameter
values for one defect still represent one behavior family. They must never be used
to make a narrow exercise appear deeper than it is.

For example:

- Testing an inventory race with seven stock/quantity combinations is one behavior
  family: atomic reservation.
- Testing validation, authorization, state transitions, rollback, idempotency,
  filtering, ordering, and concurrency represents eight behavior families because
  each can fail and be repaired independently.

The published catalog does not include a lower-depth profile. A narrow single-repair
exercise must be expanded into a coherent repository challenge or kept out of the
catalog.

## 2. Required design vocabulary

Challenge authors and reviewers must use these terms consistently.

### Behavioral contract

One observable rule that the system must preserve. Examples include “only the owner
may cancel an active reservation” and “a failed payment must not consume inventory.”

### Behavior family

A group of test cases that verifies one behavioral contract. Boundary values and
parameter combinations belong to the same family when they exercise the same rule
and are repaired by the same decision.

### Root cause

The underlying implementation error that violates one or more contracts. Several
failing tests may share one root cause.

### Repair decision

A meaningful design choice made by the candidate, such as validating before
mutation, enforcing a state transition, choosing per-key locking, or defining a
deterministic tie-breaker.

### Incidental change

Formatting, renaming, boilerplate, generated code, or repeated case handling that
does not add an engineering decision. Incidental changes do not count toward depth.

## 3. Challenge depth profiles

The following are minimum editorial targets, not automatic substitutes for review.

| Level | Timebox | Behavior families | Distinct root causes | Expected repository surface |
|---|---:|---:|---:|---|
| Easy | 20–30 min | 3–4 | 2+ | One workflow across one or two files |
| Medium | 30–45 min | 5–7 | 3+ | Multiple methods or components with interacting contracts |
| Hard | 45–60 min | 7+ | 4+ | Cross-component reasoning, evidence, or non-trivial tradeoffs |

Solution line count is only a diagnostic signal. As a review heuristic, a Medium
repository exercise that is completely solved by one obvious ten-line change should
be expanded or rejected. A small patch may still be acceptable when discovering and
justifying it requires substantial evidence interpretation and the challenge meets
the behavior-family and root-cause minimums; patch size alone never waives those
minimums.

## 4. Question specification

Every planned challenge must have a written specification before implementation.
The specification must contain the following sections.

### Candidate question

Describe:

- the product or operational context;
- the observable failure;
- the candidate’s objective;
- constraints that a valid repair must preserve;
- the command used to run the tests.

The question must not name the exact bug, prescribe the algorithm, identify the
precise line to change, or leak the reference solution.

### Required behavior

List each behavioral contract separately. The list must be specific enough to review
the test suite against it without reading the reference implementation.

Good contracts describe externally visible outcomes:

- “Cancellation releases every seat in the reservation.”
- “Concurrent requests for unrelated keys remain independent.”
- “Equal timestamps are ordered by the stable record identifier.”

Weak contracts describe implementation details:

- “Add a lock.”
- “Use `sorted()`.”
- “Call the repository twice.”

### Repository and evidence

State what the candidate receives:

- editable source files;
- read-only tests;
- fixtures, logs, schemas, traces, or policy documents;
- relevant runtime and dependency constraints.

Every provided file must contribute to the investigation or realistic context.
Decorative files that exist only to make the repository look larger are prohibited.

### Grading contract

Map every required behavior to one or more tests. Identify which behaviors should
already pass in the starter and which should fail. A reviewer must be able to tell
whether a test is protecting a distinct rule or merely repeating an existing case.

### Interview signal

Explain what strong candidate behavior looks like, including:

- how they should navigate the repository;
- which invariants they should identify;
- which tradeoffs they should discuss;
- what incomplete or dangerous fixes they may propose.

## 5. Starter repository standard

The starter repository must be plausible code that could survive an ordinary code
review before failing under a missing edge case, production condition, or more exact
contract.

It must:

- contain meaningful working behavior;
- fail because of realistic implementation decisions, not random sabotage;
- expose enough domain structure for the candidate to reason about ownership,
  lifecycle, data flow, or concurrency;
- remain small enough to understand within the stated timebox;
- keep tests, fixtures, dependency manifests, and evidence read-only;
- avoid TODO-only skeletons unless implementation from a specification is the
  explicit exercise type.

For multi-bug challenges, defects should interact through a coherent workflow. Do
not combine unrelated trivia merely to increase the number of failures.

## 6. Test-suite standard

The existing platform requirements remain mandatory:

- at least 15 collected test cases;
- between 1 and 5 passing cases in the untouched starter;
- the configured pristine pass percentage for the challenge difficulty;
- every test passes after applying the reference solution.

Those numerical checks are necessary but insufficient. A publishable suite must also
meet these semantic requirements.

### Behavioral coverage

- Every required behavior has at least one direct test.
- Medium challenges have at least five behavior families.
- Hard challenges have at least seven behavior families.
- No single behavior family should account for more than 40% of the failing cases.
- Parameterized cases must cover meaningful boundaries rather than repeat equivalent
  inputs to reach the minimum count.
- At least one test protects important behavior that already works in the starter.
- At least one test rejects a tempting but incomplete repair.

### Test quality

Tests must be:

- deterministic and offline;
- named after observable behavior;
- independent of execution order;
- explicit about state before and after mutation;
- free from real sleeps when barriers, fake clocks, injected schedulers, or events can
  control the interleaving;
- free from network services and machine-specific configuration;
- behavior-focused rather than coupled to internal call order, private helpers, or a
  particular reference implementation.

### Required coverage matrix

Every new or substantially revised challenge must include this matrix in its design
review notes or question-bank entry:

| Behavior family | Starter state | Tests | Root cause | Incomplete fix rejected |
|---|---|---|---|---|
| Example: ownership | Failing | owner cancel; non-owner cancel | Missing authorization check | Status-only validation |

A large number of rows sharing the same root cause is visible evidence that the
challenge may be narrower than its test count suggests.

## 7. Reference solution standard

The reference solution is executable proof that the complete contract is coherent.
It must:

- repair root causes rather than special-case fixtures;
- make the entire suite pass without modifying protected tests;
- preserve all starter behavior that was already correct;
- validate a request completely before performing irreversible or externally visible
  mutation where atomicity is part of the contract;
- use production-defensible state transitions, authorization boundaries, ordering,
  isolation, and failure handling;
- avoid unnecessary refactors that obscure the essential repair;
- contain only files that genuinely differ from the starter repository.

The solution does not need to be the only valid implementation. It should be the
clearest defensible implementation for teaching and comparison.

### Cross-language variants

Language variants must preserve behavioral parity, not line-for-line parity.

Each variant must independently satisfy:

- the same product scenario and required behaviors;
- equivalent difficulty and timebox;
- the same behavior-family coverage;
- idiomatic runtime-specific concurrency and error handling;
- its own passing reference solution and package audit.

A variant must not ship merely because the source was mechanically translated.

## 8. Solution walkthrough standard

Every `SOLUTION.md` must use this structure unless the challenge type requires a
clearly justified variation.

```markdown
# <Challenge title> solution

## Problem summary

## Starter bugs fixed

## Corrected behavior

## Edge cases covered

## What to watch for

## Why the fix works

## Tradeoffs and production considerations

## Interview talking points
```

### Problem summary

Restate the domain and the system’s responsibilities without repeating the candidate
brief verbatim.

### Starter bugs fixed

Describe every distinct defect and its consequence. Do not collapse several bugs into
“fixed validation” or “handled edge cases.”

### Corrected behavior

Explain the final end-to-end contract in plain language.

### Edge cases covered

Name the important boundaries and failure paths proven by tests.

### What to watch for

Describe plausible incomplete repairs and why they fail. This section should teach
the learner how to review their own approach.

### Why the fix works

Connect implementation decisions to invariants. Do not merely narrate changed lines.

### Tradeoffs and production considerations

Discuss realistic alternatives, costs, scaling limits, database equivalents, or
operational consequences.

### Interview talking points

Give the learner concise language for explaining the diagnosis and repair.

The product solution page owns the code-change presentation. It must show one
authoritative diff from **Starter code** to **Official solution**, with file change
statistics and collapsible files. It must not imply that test count equals solution
complexity.

## 9. Anti-patterns that block publication

A challenge must be revised, relabeled, or rejected when any of these are true:

- Most failing tests are parameterized copies of one invariant.
- The advertised difficulty is supported only by test count.
- A Medium or Hard challenge is solved by an obvious local edit with no meaningful
  diagnosis or tradeoff.
- The starter brief is vague because the tests are expected to explain everything.
- The brief reveals the exact repair rather than the required behavior.
- Tests assert mocks, private helpers, call order, or implementation shape instead of
  product behavior.
- The reference solution weakens assertions, skips cases, catches every exception, or
  hard-codes fixture outputs.
- Multiple bugs are unrelated trivia rather than parts of one coherent workflow.
- Repository files exist only to create artificial navigation work.
- A language variant has fewer behaviors or an easier repair than the base challenge.
- `SOLUTION.md` describes only the happy path or only the code diff.

## 10. Editorial review rubric

Score each category from 0 to 2:

- **0:** missing or unacceptable;
- **1:** present but shallow, ambiguous, or incomplete;
- **2:** clear, realistic, and review-ready.

| Category | Review question |
|---|---|
| Scenario | Does this resemble a credible backend engineering task? |
| Contract | Are the observable requirements precise and non-leaking? |
| Depth | Are there enough independent behaviors and repair decisions? |
| Starter | Is the broken code plausible and partially functional? |
| Tests | Do tests prove contracts rather than implementation details? |
| Determinism | Are time, concurrency, I/O, and ordering controlled? |
| Solution | Does the reference fix root causes and preserve invariants? |
| Walkthrough | Does it explain every bug, edge case, and incomplete fix? |
| Difficulty | Does the work match the stated timebox and label? |
| Variants | Are language variants behaviorally equivalent and idiomatic? |

Publication requires:

- no category scored 0;
- at least 17/20 overall;
- a score of 2 for Contract, Tests, Solution, and Difficulty;
- reviewer sign-off on the behavior coverage matrix.

## 11. Authoring workflow

1. Write the candidate question and required behaviors.
2. Build the behavior coverage matrix.
3. Choose realistic interacting root causes.
4. Estimate difficulty from decisions and repository exploration—not test count.
5. Build the smallest realistic starter repository.
6. Write tests from the behavioral contracts.
7. Confirm the pristine suite fails for the intended reasons.
8. Implement the reference solution without touching protected tests.
9. Confirm every behavior family passes.
10. Write the structured solution walkthrough.
11. Run package, pristine, solution, and full-catalog validation.
12. Complete the editorial rubric with a reviewer.

Do not begin by writing 15 tests and then inventing a question around them.

## 12. Definition of done

A challenge is ready only when all of the following are true:

- The question specification contains every required section.
- The behavior matrix meets the depth target.
- The starter fails for intentional, documented root causes.
- Passing starter behavior is meaningful and remains protected.
- Test cases are deterministic, offline, and behavior-focused.
- Every runtime dependency exists in the production execution image.
- The reference overlay passes the complete suite.
- The solution walkthrough follows the required structure.
- Every solution claim maps to code and at least one test.
- All language variants meet the same contract independently.
- The editorial rubric passes.
- The repository validator and relevant application suites pass.

## 13. Existing-catalog audit

Existing challenges should be reviewed and assigned one outcome:

1. **Keep:** already meets the standard.
2. **Reclassify:** meets the minimum standard but its current Easy, Medium, or Hard
   difficulty or timebox is inaccurate.
3. **Expand:** strong scenario that needs more independent contracts and root causes.
4. **Retire or replace:** duplicate, artificial, or below the Easy minimum.

For each challenge, record behavior families, distinct root causes, solution files,
meaningful solution delta, and rubric score. Test count alone must not determine the
outcome.

The audit record lives in [CHALLENGE_AUDIT.md](CHALLENGE_AUDIT.md). `orders-service`
was the first completed audit: it was expanded from one repeated locking decision into
a multi-contract checkout workflow. Apply the same semantic review to the remaining
catalog in order; validator success alone does not change an entry from pending.
