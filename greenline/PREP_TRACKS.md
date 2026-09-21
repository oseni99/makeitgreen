# MakeItGreen prep tracks

Use these paths as a curriculum, not a ranking. Move on when you can explain
the invariant you restored, the evidence you used, and one production tradeoff.

## Backend foundations

For engineers new to repository interviews. Target: 6–8 sessions.

1. `wallet-service` — read tests as the specification.
2. `return-workflow` — preserve state-machine invariants.
3. `config-merge` — distinguish explicit overrides from missing values.
4. `log-aggregator` — reason about boundaries and data reduction.
5. `ledger-api` — implement status and idempotency contracts.
6. `token-auth-api` — keep credentials and capabilities exact.
7. `cache-ext` — extend a working service through a narrow interface.
8. `runbook-revisions` — combine lifecycle policy with optimistic updates.
9. `notification-dispatch-node` — extend a FIFO contract in Node.js.
10. `auth-tenant-leak` — keep direct lookups and caches inside the tenant boundary.
11. `feature-flag-ext` — add a last-known-good runtime client around a working source.

## Concurrency and distributed correctness

For backend interviews where retries, races, and consistency matter. Target:
6–8 sessions.

1. `orders-service` — preserve stock and order lifecycles under concurrency and retries.
2. `transfer-deadlock` — establish a global lock order.
3. `rate-limiter` — make admission atomic and tenant-scoped.
4. `job-lease` — fence stale workers after lease expiry.
5. `invoice-delivery-worker` — combine idempotency, acknowledgement, and backoff.
6. `workspace-replica-router` — preserve read-your-writes across replicas.
7. `invoice-cents-migration` — perform online dual-write migration safely.
8. `digest-scheduler` — use leases and fencing generations for singleton work.
9. `device-command-webhook` — layer idempotency over per-device ordering.

## Production debugging

For incident, database, and runtime rounds. Target: 8–10 sessions.

1. `incident-alerts` — trace symptoms through logs and time windows.
2. `queue-drain` — quarantine poison data without stopping the stream.
3. `deploy-crash` — diagnose a startup failure from evidence.
4. `device-ingest-incident` — isolate poison data without stopping the stream.
4. `audit-export-pool` — clean up transactions and pooled resources.
5. `thread-stall` — read thread evidence and remove pool starvation.
6. `build-stream-leak` — follow a retaining path and repair lifecycle cleanup.
7. `topk-errors` — trade exactness for bounded memory.
8. `enrichment-timeout-incident` — turn evidence into a bounded fallback.
9. `audit-archive-stream` — distinguish retention spikes from leaks.
10. `thumbnail-handoff` — repair condition-variable waiting and shutdown.
11. `profile-search-projector` — reason about CDC visibility and atomic checkpoints.
12. `lab-sample-history` — scope revision and transition windows by full identity.
13. `csv-import` — separate file corruption from recoverable row failures.
14. `retry-storm` — classify failures and respect retry budgets and backpressure.
15. `gc-churn` — turn allocation evidence into bounded expensive work.
16. `cdc-slot` — retain changes until every active consumer acknowledges them.

## Senior mixed loop

Use this as a five-session mock onsite. Timebox each challenge, then review the
reference solution only after recording your diagnosis.

1. `pagination-api` — API contract debugging, 25 minutes.
2. `subscription-renew` — multi-bug repository repair, 45 minutes.
3. `artifact-upload-ext` — architecture extension, 45 minutes.
4. `outbox-publish` — transactional delivery, 35 minutes.
5. `build-stream-leak` — runtime diagnostics, 40 minutes.
6. `vendor-catalog-reconcile` — multi-source identity and conflict policy, 40 minutes.
7. `cdc-slot` — multi-consumer retention and acknowledgement fencing, 40 minutes.

## Difficulty ladder

- **Easy:** identify one local invariant and make a focused correction.
- **Medium:** coordinate two or more behaviors across module boundaries.
- **Hard:** protect interacting invariants under failure, retries, concurrency,
  or partial progress. Explain why the fix remains safe beyond the visible test.

Recommended progression is two Easy challenges, four Medium challenges from
different types, then one Hard challenge. Revisit a solved challenge without
the solution after one week to test retention rather than recognition.
