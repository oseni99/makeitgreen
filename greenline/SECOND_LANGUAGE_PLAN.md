# Second-language runtime: Node.js

Node is available in two forms: standalone Node-native concepts and alternate
language implementations of existing concepts. `webhook-batch-node` and
`notification-dispatch-node` remain standalone because their scenarios are designed
around Node. Six concepts now offer a Python/JavaScript choice:

- `orders-service` — asynchronous inventory race;
- `wallet-service` — money invariants and atomic failure;
- `config-merge` — recursive merging without truthiness bugs or mutation;
- `token-auth-api` — exact credential and capability matching;
- `pagination-api` — stable opaque keyset pagination;
- `retry-storm` — classified retries, backpressure, and attempt budgets.

Together, the paired concepts and two Node-native exercises provide eight runnable
JavaScript interview challenges across concurrency, repository implementation, API
contract debugging, incident debugging, and architecture extension.

## Language-variant product contract

- The catalog shows one card per interview concept, with compact language choices.
- The base slug remains the default implementation (`orders-service` is Python).
- Additional implementations use `<slug>@<variant>` as their API and persistence key
  (`orders-service@javascript`). Files, runs, attempts, spoilers, and debriefs are
  isolated per implementation.
- Concept progress is solved when any implementation is solved and attempted when any
  implementation is attempted. Variant-level progress remains visible on each choice.
- A variant can override only language-specific presentation, edit boundaries, timing,
  and runtime policy. It cannot silently change the concept identity or catalog order.
- Every starter and solution pair is independently validated red/green.

The representative beta set is complete. Expanding the remaining concepts should be
driven by beta demand and retain this review bar; it is a content project, not a
mechanical transpilation task.

## First challenge: `webhook-batch-node`

- **Type:** Repository Implementation
- **Difficulty:** Medium
- **Timebox:** 30 minutes
- **Runtime:** Node.js 22+
- **Test command:** `node --test`
- **Dependencies:** none; it uses Node's built-in test runner
- **Scenario:** a webhook batcher groups events by tenant before delivery.
- **Broken behaviors:** batches leak across tenants, the maximum batch-size
  boundary is off by one, and a failed delivery removes events before a retry.
- **Candidate surface:** `src/batcher.js`; `test/` is read-only.
- **Determinism:** injected sender, no network, no wall-clock waits.

### Acceptance tests

1. preserve input order within each tenant;
2. never mix tenant IDs in one delivery;
3. flush exactly at the configured batch size;
4. retain a failed batch for an identical retry;
5. acknowledge and remove a successful batch once;
6. keep one tenant's failure from blocking another tenant.

## Second challenge: `notification-dispatch-node`

- **Type:** Architecture Extension
- **Difficulty:** Medium
- **Timebox:** 30 minutes
- **Candidate surface:** `src/queue.js`; `test/` is read-only.
- **Extension:** scheduled delivery plus stable urgency ordering over a working FIFO queue.
- **Key invariant:** filter by `deliverAt <= now` before comparing urgency, then break
  ties by insertion sequence.
- **Determinism:** `take(now)` receives time explicitly; no packages, network, or sleeps.

## Implemented runner contract

The challenge uses this validated runtime declaration:

```json
{
  "runtime": {
    "kind": "node",
    "command": ["node", "--test"],
    "report": "text"
  }
}
```

The runner and catalog validator now:

1. validate the runtime kind and command shape; commands come only from reviewed,
   repository-owned challenge metadata and never from a candidate request;
2. execute in the copied temporary repository with the existing 60-second process-group timeout;
3. keep the current Node challenges dependency-free (Python challenges separately support
   cached `runtime.requirements` environments);
4. parse Node TAP summary counts into the existing aggregate result schema; structured
   per-test locations remain a pytest capability for now;
5. enforce the same ignored files, editable paths, output cap, and cleanup rules;
6. validate pristine exit 1 and solution-overlay exit 0 using the declared runtime;
7. install Node 22 in CI for full-catalog validation.

Future Node challenges should reuse this contract. Before accepting npm dependencies,
add a lockfile-backed, content-addressed install cache with the same concurrency and
invalidation guarantees as the Python environment cache.
