# Second-language runtime: Node.js

Two dependency-free Node challenges are live: `webhook-batch-node` at catalog order 29
and `notification-dispatch-node` at order 33. Both use Node's built-in test runner and
the platform's validated runtime metadata.

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
