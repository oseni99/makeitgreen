# MakeItGreen existing-catalog audit

This document tracks the review of every published challenge against
[CHALLENGE_AUTHORING_STANDARD.md](CHALLENGE_AUTHORING_STANDARD.md). Passing the
repository validator is necessary, but it does not prove that a challenge contains
enough independent engineering decisions. Each entry therefore records behavior
families, root causes, incomplete fixes, cross-language parity, and an editorial
verdict.

## Status vocabulary

- **Keep:** meets the current standard.
- **Reclassify:** sound challenge, inaccurate difficulty or timebox.
- **Expand:** useful scenario, insufficient independent depth.
- **Retire or replace:** artificial, duplicative, or below the Easy minimum.
- **Pending audit:** not yet reviewed semantically under the current standard.

## Audit queue

The catalog is reviewed in order so learners encounter corrected early challenges
first. One challenge is completed and validated before the next begins; broad
mechanical rewrites are prohibited.

| Order | Challenge | Audit state | Current decision |
|---:|---|---|---|
| 1 | `orders-service` | Complete | Keep after expansion |
| 2 | `wallet-service` | Reviewed | Expand |
| 3–10 | `ledger-api` through `pagination-api` | Pending audit | — |
| 11–20 | `deploy-crash` through `audit-export-pool` | Pending audit | — |
| 21–30 | `device-ingest-incident` through `runbook-revisions` | Pending audit | — |
| 31–40 | `digest-scheduler` through `csv-import` | Pending audit | — |
| 41–49 | `auth-tenant-leak` through `queue-drain` | Pending audit | — |

For every completed entry, record the exact pristine and solved counts for every
language variant. A challenge does not leave “Pending audit” merely because its old
tests still pass.

## `orders-service` — complete

### Outcome

**Keep after expansion.** The former version had 18 cases but thirteen failures
collapsed to one stock-locking decision. The revised medium challenge is a complete
checkout lifecycle with seven behavior families and several interacting failure
modes. The timebox increased from 25 to 40 minutes.

### Candidate task

Repair a flash-sale checkout workflow so input validation, pricing, reservation,
retries, error recovery, and cancellation remain consistent under concurrent calls.
The public API and concurrency between unrelated SKUs must be preserved.

### Behavior coverage matrix

| Behavior family | Starter state | Direct tests | Root cause | Incomplete fix rejected |
|---|---|---|---|---|
| Order input contract | Mixed | positive quantity; blank SKU; zero/negative price | Incomplete boundary validation | Validating quantity only |
| Pricing | Passing | exact discount boundaries; repeated application | Already correct | Recomputing from a discounted total |
| Reservation contract | Mixed | insufficient stock; zero quantity | Missing quantity validation | Treating zero as a harmless no-op |
| Atomic stock mutation | Failing | last unit; pairs; remainder | Check and write separated across authorization | Locking only the final write without rechecking |
| Partition independence | Passing | GPU and CPU authorize concurrently | Already correct and must remain correct | One global inventory lock |
| Checkout idempotency and recovery | Failing | completed retry; rejected retry; authorization error; simultaneous retry | Terminal state and side effects are not one per-order decision | Unsynchronized early status checks |
| Cancellation lifecycle | Failing | completed cancel; pre-completion cancel; repeated cancel | Missing state guard and stock compensation | Restocking without a terminal transition |

No behavior family contributes more than 40% of the failing cases. The passing tests
protect meaningful creation, pricing, insufficient-stock, and partition-independence
behavior.

### Root causes and repair decisions

1. Order and reservation boundaries were only partially validated.
2. Stock validation and mutation trusted state observed before an authorization
   interleaving.
3. Order status inspection was not serialized with checkout side effects.
4. Unexpected exceptions had no explicit recovery transition.
5. Cancellation ignored lifecycle state and inventory compensation.

The reference implementations use per-SKU synchronization for stock and per-order
synchronization for lifecycle decisions. Python uses locks; JavaScript uses promise
tails. Both authorize before the SKU critical section and recheck stock inside it.

### Variant evidence

| Variant | Pristine | Official solution | Dependency audit |
|---|---:|---:|---|
| Python | 5 passed, 14 failed | 19 passed | Standard library + pytest available |
| JavaScript | 5 passed, 14 failed | 19 passed | Node built-ins only |

Both suites use barriers or promise gates rather than timing sleeps. Both preserve the
same product contract, difficulty, terminal states, and per-key concurrency.

### Editorial rubric

| Category | Score | Evidence |
|---|---:|---|
| Scenario | 2 | Credible flash-sale checkout lifecycle |
| Contract | 2 | Eight explicit externally visible rules |
| Depth | 2 | Seven behavior families and five root causes |
| Starter | 2 | Plausible partially working orchestration |
| Tests | 2 | Behavior-focused cases reject narrow fixes |
| Determinism | 2 | Barriers and promise gates; no network or sleeps |
| Solution | 2 | Repairs validation, synchronization, recovery, and compensation |
| Walkthrough | 2 | Full required solution structure in both variants |
| Difficulty | 2 | Medium, 40 minutes matches the expanded scope |
| Variants | 2 | Equivalent idiomatic Python and JavaScript designs |
| **Total** | **20/20** | Publication gate passed |

### Validation commands

```bash
backend/venv/bin/python -c \
  "from scripts.validate_challenges import validate_challenge; validate_challenge('orders-service')"

backend/venv/bin/python -c \
  "from scripts.validate_challenges import validate_challenge; validate_challenge('orders-service@javascript')"
```

Both variants pass pristine/solution validation and the 15-test, 1–5-pass, and
pristine-percentage gates.

## `wallet-service` — reviewed, expansion required

### Outcome

**Expand.** The scenario is credible and both variants are deterministic, but the
current 15 cases overstate the exercise depth. Twelve failures are repeated boundary
values for two local defects, and the official repair changes only the minimum-fee
expression and the sufficient-funds guard.

### Current behavior coverage

| Behavior family | Current cases | Result | Audit finding |
|---|---:|---|---|
| Basic deposits and balances | 1 | Passing | Useful protected behavior |
| Invalid positive-amount boundary | 1 | Passing | Useful but narrow validation |
| Ordinary transfer accounting | 1 | Passing | Useful protected happy path |
| Minimum transfer fee | 6 | Failing | One rule repeated across equivalent sub-dollar values |
| Sender covers amount plus fee | 6 | Failing | One guard repeated across near-balance values |

The two failing families each account for 50% of all failures, above the 40% limit.
The challenge reaches 15 cases through parameter volume rather than three or four
independent Easy-level decisions.

### Required revision

Keep the wallet domain and integer-cents contract, but add coherent account and
transfer rules rather than more fee values. The revised design should cover:

1. account identity and duplicate-open behavior;
2. deposit and transfer amount validation;
3. exact integer fee calculation, including the minimum;
4. distinct source/destination and complete-debit validation;
5. all-or-nothing balance and fee accounting.

Python and JavaScript must retain behavioral parity. The revision needs a new coverage
matrix, structured walkthroughs, 1–5 meaningful passing cases, and official solutions
that pass every case in both runtimes.
