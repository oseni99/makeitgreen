# MakeItGreen — Researched Question Bank

This document contains original MakeItGreen challenge specifications derived from
general backend-engineering themes and checked against primary technical sources.
External problem collections are research inputs only: do not copy their prose,
fixtures, repositories, tests, solutions, names, or domain stories.

**Status:** all three research batches are fully implemented.
**Catalog baseline:** 49 live challenges; all Q1–Q26 specifications are live. The fourth batch adds four original exercises outside the researched question bank.
**Original batch language:** Python. The second batch deliberately adds another Node
exercise now that runtime metadata and catalog validation support it.

## Batch overview

| Bank ID | Catalog order | Slug | Type | Difficulty | Minutes | Status |
|---:|---:|---|---|---|---:|---|
| Q1 | 19 | `project-vault-api` | API Contract Debugging | Medium | 30 | ✅ live |
| Q2 | 22 | `invoice-delivery-worker` | Concurrency | Hard | 40 | ✅ live |
| Q3 | 23 | `release-gates` | Architecture Extension | Hard | 40 | ✅ live |
| Q4 | 24 | `invoice-cents-migration` | Database Engineering | Hard | 40 | ✅ live |
| Q5 | 20 | `audit-export-pool` | Database Engineering | Medium | 30 | ✅ live |
| Q6 | 25 | `workspace-replica-router` | Database Engineering | Hard | 40 | ✅ live |
| Q7 | 26 | `build-stream-leak` | Runtime Diagnostics | Hard | 40 | ✅ live |
| Q8 | 27 | `artifact-upload-ext` | Architecture Extension | Hard | 45 | ✅ live |
| Q9 | 21 | `device-ingest-incident` | Incident Debugging | Medium | 30 | ✅ live |
| Q10 | 18 | `return-workflow` | Repository Implementation | Easy | 20 | ✅ live |

## Second batch overview

These specifications use the public machine-coding collection as a theme map, then
change the domain, repository shape, failure combination, and grading contract for
MakeItGreen. Catalog orders are reservations, not live entries.

| Bank ID | Planned order | Slug | Type | Difficulty | Minutes | Status |
|---:|---:|---|---|---|---:|---|
| Q11 | 30 | `runbook-revisions` | Repository Implementation | Medium | 30 | ✅ live |
| Q12 | 31 | `digest-scheduler` | Concurrency | Hard | 40 | ✅ live |
| Q13 | 32 | `profile-search-projector` | Database Engineering | Hard | 40 | ✅ live |
| Q14 | 33 | `notification-dispatch-node` | Architecture Extension | Medium | 30 | ✅ live |
| Q15 | 34 | `device-command-webhook` | API Contract Debugging | Hard | 40 | ✅ live |
| Q16 | 35 | `enrichment-timeout-incident` | Incident Debugging | Medium | 30 | ✅ live |
| Q17 | 36 | `audit-archive-stream` | Runtime Diagnostics | Hard | 35 | ✅ live |
| Q18 | 37 | `thumbnail-handoff` | Runtime Diagnostics | Hard | 40 | ✅ live |
| Q19 | 38 | `vendor-catalog-reconcile` | Repository Implementation | Hard | 40 | ✅ live |
| Q20 | 39 | `lab-sample-history` | Database Engineering | Hard | 40 | ✅ live |

## Third batch overview

The third batch converts the former Tier 3 backlog into six original repositories.

| Bank ID | Catalog order | Slug | Type | Difficulty | Minutes | Status |
|---:|---:|---|---|---|---:|---|
| Q21 | 40 | `csv-import` | Incident Debugging | Medium | 30 | ✅ live |
| Q22 | 41 | `auth-tenant-leak` | API Contract Debugging | Medium | 30 | ✅ live |
| Q23 | 42 | `retry-storm` | Incident Debugging | Medium | 30 | ✅ live |
| Q24 | 43 | `feature-flag-ext` | Architecture Extension | Medium | 30 | ✅ live |
| Q25 | 44 | `gc-churn` | Runtime Diagnostics | Medium | 30 | ✅ live |
| Q26 | 45 | `cdc-slot` | Database Engineering | Hard | 40 | ✅ live |

---

## Q1. `project-vault-api`

**Type:** API Contract Debugging
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

You inherit the document API for a multi-tenant project workspace. Authentication is
already implemented: each request carries a verified principal with a user ID and a
workspace ID. The document handlers accept project and document IDs from the URL.

Several contract tests are red. A member of one workspace can retrieve metadata from
another workspace by changing an ID, a project viewer can rename files, and one denial
path serializes the protected document before returning an error.

Repair the authorization boundary without changing the route shapes or response
schema. Preserve legitimate member and administrator behavior.

### Required behavior

- Every document lookup is scoped by the authenticated workspace and containing
  project, not by document ID alone.
- Project viewers may read documents but may not rename or delete them.
- Project editors may read and rename; workspace administrators may also delete.
- Missing or invalid credentials produce `401`; valid credentials without the
  required permission produce `403`.
- Requests for absent documents within an authorized project produce `404`.
- Denied responses contain no title, owner, storage key, or other protected fields.

### Repository and evidence

- Small FastAPI service with an in-memory repository.
- Read-only API contract tests and an access-control matrix in `docs/policy.md`.
- The broken repository method fetches globally by document ID; one mutation handler
  checks workspace membership but not project role.

### Grading contract

- Cross-workspace reads, renames, and deletes never expose or mutate data.
- A document ID that exists under a different project cannot satisfy the request.
- Role checks apply consistently to collection and item routes.
- Tests distinguish authentication, authorization, and authorized-not-found cases.
- A regression test asserts that denial bodies contain no protected values.

### Interview signal

The candidate should centralize resource-scoped authorization and make the repository
query itself tenant-aware. Scattered route-level ID comparisons or filtering the
response after a global lookup leave the actual boundary unsafe.

---

## Q2. `invoice-delivery-worker`

**Type:** Concurrency
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A billing service delivers finalized invoices to customer accounting integrations.
Workers pull delivery commands from an at-least-once queue. The external delivery is
represented by a deterministic in-process sink, and time is supplied by a fake clock.

Under retries and multiple workers, customers receive duplicate invoices. Transient
failures are placed straight back on the hot queue, so workers spin continuously, and
a crash after delivery but before acknowledgement repeats the side effect.

Make delivery retry-safe while preserving parallel processing for unrelated invoices.

### Required behavior

- A command has a stable message ID; applying the same command again does not repeat
  its delivery side effect.
- Successful delivery and the processed-message record become visible atomically.
- Transient failures are scheduled using the provided clock and exponential delays of
  1, 2, 4, then 8 seconds.
- A command is attempted at most five times and is then parked with its final error and
  attempt history.
- Messages whose retry time is in the future do not block ready work.
- Two workers racing on the same command still produce one delivery.

### Repository and evidence

- In-memory queue, transactional state store, delivery sink, and injected clock.
- Read-only tests coordinate workers with barriers; no real sleeps or network calls.
- The broken worker acknowledges before recording its effect and immediately requeues
  all failures.

### Grading contract

- Concurrent duplicate delivery has exactly one observable effect.
- A simulated crash at each boundary can be retried safely.
- Backoff timing is deterministic and capped by the specified schedule.
- The fifth failed attempt parks the command once and removes it from normal work.
- A delayed failure does not prevent a later ready command from completing.

### Interview signal

The candidate should reason explicitly about the acknowledgement crash window,
message identity, atomic state changes, and per-message scheduling. A process-wide lock
or a larger worker pool does not establish idempotency.

---

## Q3. `release-gates`

**Type:** Architecture Extension
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A deployment service already stores feature definitions and can return a fixed default
value. Extend it with release gates for B2B workspaces. A gate may contain an emergency
disable switch, ordered attribute rules, an allowlist, and a percentage rollout.

The evaluator must be a pure, deterministic function. The same workspace should not
move between cohorts during a rollout, and two different gates must not accidentally
assign identical cohorts merely because their percentages match.

### Required behavior

- Evaluation is isolated by environment; development configuration never affects
  production.
- Emergency disable is evaluated first and always returns disabled.
- Explicit workspace allowlists precede ordered attribute rules.
- Rules use first-match semantics and support equality and membership conditions.
- Percentage rollout uses a stable bucket derived from gate key plus workspace key.
- Increasing a rollout percentage retains every workspace previously included.
- Missing context or no matching rule returns the configured default with a reason.

### Repository and evidence

- Existing flag store and result model; candidate creates an `evaluation/` package.
- Read-only tests provide fixed cohort fixtures rather than depending on Python's
  process-randomized `hash()`.
- The result includes value, reason, and matched rule ID for explainability.

### Grading contract

- Repeated evaluation and interpreter restarts yield the same cohort.
- A 20% cohort is a subset of the corresponding 40% cohort.
- Gate keys salt the bucket so equal percentages need not target identical workspaces.
- Rule ordering, environment separation, and emergency disable are independently
  tested.
- The evaluator does not mutate definitions or context.

### Interview signal

Strong solutions make precedence visible, use a stable digest with a documented bucket
range, and return evaluation metadata. Random draws, Python `hash()`, or unordered rule
containers violate the contract.

---

## Q4. `invoice-cents-migration`

**Type:** Database Engineering
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

An invoicing database stores totals as decimal strings in a legacy `amount` column.
New code expects integer `subtotal_cents`, `tax_cents`, and `total_cents` columns. The
new nullable columns already exist, but production writes continue while a background
backfill runs in small batches.

The current writer populates only the legacy column. The backfill paginates with an
offset, skips rows when the dataset changes, and records completion even when unmigrated
rows remain.

Make the expansion safe enough that a later deployment can remove the legacy field.

### Required behavior

- New invoices write both the legacy amount and all cent-based columns in one
  transaction.
- Existing invoices are migrated in bounded batches ordered by immutable invoice ID.
- Monetary conversion uses decimal arithmetic and the supplied tax breakdown; binary
  floating-point rounding is not allowed.
- A failed batch rolls back both row updates and checkpoint progress.
- Rerunning any batch is safe, including after a crash.
- Completion is reported only after querying for remaining unmigrated rows.

### Repository and evidence

- SQLite database, writer, migration runner, and injectable callback used to insert a
  row between batches.
- Read-only schema and migration contract tests.
- No destructive contract migration is part of this challenge.

### Grading contract

- Rows inserted before, between, and after batches end in a consistent dual-written
  representation.
- Sparse invoice IDs and retrying the last checkpoint do not skip or double-convert.
- A forced exception leaves neither partial row updates nor advanced progress.
- Completion cannot be spoofed by a stale checkpoint.
- Cent totals exactly reconcile with subtotal and tax.

### Interview signal

The candidate should separate expand, backfill, verification, and contract phases;
choose stable keyset progress; and keep application writes forward-compatible during
the migration window.

---

## Q5. `audit-export-pool`

**Type:** Database Engineering
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

An audit-export service borrows connections from a four-slot pool, opens a read
transaction, checks project access, and streams matching audit rows. After several
denied or malformed requests, even valid exports time out waiting for a connection.

Pool metrics and a captured session snapshot show all slots checked out, including
connections left in active or failed transactions. The pool implementation is correct;
repair the export service's ownership and transaction boundaries.

### Required behavior

- Every acquired connection is returned on success, denial, query failure, and client
  cancellation.
- Successful work commits before the connection is returned.
- Failed work rolls back before release, including failures raised during iteration.
- No released connection remains in an active or aborted transaction.
- Existing result ordering and public exceptions remain unchanged.
- Do not increase pool size, extend timeouts, or retry the entire export blindly.

### Repository and evidence

- Deterministic fake pool and connection objects that expose lifecycle counters.
- Read-only `diagnostics/pool-snapshot.txt` and `diagnostics/request-log.txt`.
- Tests inject failures before query, during iteration, and during permission checks.

### Grading contract

- Repeating every failure mode more times than pool capacity does not exhaust it.
- A valid request succeeds immediately after the failure sequence.
- Rollback precedes release on exceptional paths; commit precedes release on success.
- Cleanup is attempted exactly once per acquisition.
- Original business errors are not replaced by a cleanup implementation detail.

### Interview signal

The repair should express resource ownership structurally with a context manager or a
carefully ordered `try`/`except`/`finally`. Increasing capacity only postpones the
failure.

---

## Q6. `workspace-replica-router`

**Type:** Database Engineering
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A collaboration product serves most workspace reads from a replica. Each committed
primary write receives an increasing commit position, and the replica reports the last
position it has applied. A user who renames a workspace is sometimes redirected to a
page showing the previous name.

Routing all reads to the primary fixes correctness but violates the read-offload
requirement. Add targeted session consistency without changing the repository API.

### Required behavior

- Each session remembers the greatest commit position produced by its successful
  writes.
- A read uses the replica when its applied position satisfies the session requirement.
- A behind or unavailable replica causes that session's read to use the primary.
- Once caught up, subsequent reads return to the replica automatically.
- Sessions without writes, and unrelated sessions, continue using the replica.
- Failed writes do not advance the session watermark.

### Repository and evidence

- Deterministic primary and replica stores with manually advanced replication.
- Router responses expose the chosen source for testing and observability.
- Read-only tests cover point reads, lists, multiple sessions, and several writes.

### Grading contract

- A session observes each of its committed changes immediately.
- The watermark is monotonic across several writes.
- Equality between applied and required positions is sufficient for replica routing.
- One session's write does not pin every caller to the primary.
- Replica unavailability has an explicit fallback and does not corrupt the watermark.

### Interview signal

The candidate should distinguish session read-your-writes consistency from global
strong consistency and preserve replica offload wherever the dependency is already
satisfied.

---

## Q7. `build-stream-leak`

**Type:** Runtime Diagnostics
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A CI dashboard opens a live build stream for each browser tab. Every stream subscribes
to a process-wide event hub and captures a formatter plus a bounded snapshot buffer.
Closed tabs disappear from the active-stream registry, yet memory and event-delivery
time continue climbing throughout the day.

Use the supplied heap summary and lifecycle trace to identify and repair the retaining
path. Preserve delivery to active streams and the existing snapshot limit.

### Required behavior

- Closing a stream removes its subscription from the long-lived event hub.
- Close is idempotent and safe when initialization completed only partially.
- An active stream receives each matching build event once.
- Closed streams receive no later events and their captured buffers become collectable.
- Publishing concurrently with close does not raise or corrupt the subscriber set.
- Retained subscriber count depends on currently open streams, not historical opens.

### Repository and evidence

- Thread-safe event hub, stream service, and fake browser sink.
- Read-only `diagnostics/heap-summary.txt`, `diagnostics/retaining-path.txt`, and
  `diagnostics/lifecycle.log`.
- Tests use barriers and weak references; they do not rely on memory-size timing.

### Grading contract

- Thousands of open/close cycles return subscriber and retained-buffer counts to the
  baseline.
- Double close and constructor failure both clean up safely.
- Concurrent publish/close has defined at-most-once delivery and no collection
  mutation error.
- Active subscription behavior and bounded history remain unchanged.

### Interview signal

The candidate should follow the retaining path to the publisher and restore symmetry
between subscription and teardown. Forcing garbage collection cannot reclaim objects
that are still strongly reachable.

---

## Q8. `artifact-upload-ext`

**Type:** Architecture Extension
**Difficulty:** Hard
**Timebox:** 45 minutes

### Candidate question

A build-artifact registry already stores small immutable artifacts by content digest.
Extend it to accept interrupted large uploads without replacing the existing storage
or deduplication path.

Clients start an upload, send numbered chunks in any order, inspect progress, and later
finalize or cancel. Network retries can resend a chunk. Finalization must verify the
declared manifest before publishing an artifact.

### Required behavior

- `begin(name, size, sha256)` creates an isolated upload session.
- `put_chunk(session_id, number, data, sha256)` accepts out-of-order chunks and treats
  an identical retry as a no-op.
- Reusing a chunk number with different bytes is rejected without damaging the
  previously accepted chunk.
- `status(session_id)` returns received chunk numbers and byte count in stable order.
- `finalize(session_id, ordered_numbers)` rejects gaps, duplicate numbers, size
  mismatch, and digest mismatch.
- Successful finalization passes the assembled bytes through the existing immutable
  artifact store, preserving content deduplication.
- `cancel` is idempotent and releases all session state.

### Repository and evidence

- Correct single-upload artifact store plus stubbed `uploads/` extension package.
- Injected digest helper and in-memory session repository.
- Tests cover interruption by constructing a second service over the same repository.

### Grading contract

- Chunks can arrive in any order and status supports deterministic resume.
- Chunk and full-artifact checksums are both enforced.
- Failed finalization leaves the session available for correction.
- Successful finalization and cancellation make the session terminal.
- Uploading bytes already in the artifact store returns the existing artifact ID.

### Interview signal

Strong solutions model upload sessions explicitly, validate before publication, and
converge on the existing content-addressed storage path instead of creating a second
artifact implementation.

---

## Q9. `device-ingest-incident`

**Type:** Incident Debugging
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

At 02:17 UTC, a telemetry consumer entered a restart loop and device-event lag began
climbing. The captured log shows the same event ID immediately before every restart.
The worker reads newline-delimited sensor events and updates per-device counters.

Reproduce the incident from the supplied fixture, prevent one permanently invalid
event from terminating the batch, and quarantine rejected events with an actionable
reason. Valid traffic surrounding the bad event must continue in its original order.

### Required behavior

- Failure handling is scoped to one event; the worker continues draining the batch.
- Valid events update the correct device exactly once and in input order.
- Invalid events are quarantined with event ID, raw payload, and one stable reason:
  `invalid_json`, `missing_device`, `unknown_metric`, or `invalid_measurement`.
- Quarantined events do not mutate device state.
- Several invalid events, including consecutive ones, are all captured.
- An empty batch and a fully valid batch preserve existing behavior.

### Repository and evidence

- Read-only `logs/worker.log`, `runbook.md`, and `fixtures/incident.ndjson`.
- In-process queue, state store, and quarantine sink.
- The broken loop catches exceptions outside the per-event boundary.

### Grading contract

- The incident fixture drains completely and reproduces the expected counters.
- The repeated event is quarantined once rather than retried forever.
- Each validation failure maps to a deterministic reason.
- No broad exception handler hides unexpected infrastructure or programmer failures.
- Valid events before and after invalid input are observable in order.

### Interview signal

The candidate should start from evidence, isolate permanent data failures from system
failures, and move the recovery boundary to the individual event without turning all
exceptions into silent data loss.

---

## Q10. `return-workflow`

**Type:** Repository Implementation
**Difficulty:** Easy
**Timebox:** 20 minutes

### Candidate question

An online retailer tracks merchandise returns. The service can open a return, record
warehouse steps, cancel an early request, and list its history. Most operations work,
but invalid transitions are accepted and rejected actions sometimes appear in the
audit trail.

Implement the return lifecycle as an explicit state machine while preserving the
service API.

### Required behavior

- A return begins at `requested`.
- The normal path is `requested → authorized → received → inspected → refunded`.
- Inspection may instead end at `rejected`; both `refunded` and `rejected` are
  terminal.
- Cancellation is allowed only from `requested` or `authorized` and is terminal.
- Skipped, repeated, and backward transitions are rejected with `InvalidTransition`.
- Only successful transitions append to history; rejected attempts leave state and
  history unchanged.
- History entries receive increasing sequence numbers and list deterministically.

### Repository and evidence

- Small in-memory return repository and partially implemented service.
- Read-only tests serve as the primary specification.
- No HTTP framework, database, threads, or wall clock is needed.

### Grading contract

- Every legal branch and terminal state is covered.
- Unknown return IDs and invalid transitions use distinct exceptions.
- Rejected operations are atomic no-ops.
- Listings remain stable when multiple returns exist.
- Transition policy has one source of truth rather than scattered conditionals.

### Interview signal

The candidate should define allowed transitions before coding and route every state
change through the same enforcement point. The exercise tests precision and
maintainability rather than framework knowledge.

---

## Q11. `runbook-revisions`

**Type:** Repository Implementation
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

An operations portal stores incident runbooks that move through draft, review,
approved, active, and retired states. Editors can revise instructions while reviewers
approve a known version. Production reports show stale browser tabs overwriting newer
edits, old snapshots changing after later edits, and rollback erasing the audit trail.

Repair the workflow without changing its public service interface.

### Required behavior

- Every accepted edit appends an immutable snapshot with a monotonic revision number.
- An edit or approval includes the revision the caller observed and rejects stale input.
- Only documented lifecycle transitions are accepted.
- Activating a scheduled revision before its effective time is a no-op.
- Rollback creates a new revision containing earlier instructions; it never deletes or
  rewrites history.
- Rejected operations leave both current state and history unchanged.

### Repository and grading contract

- In-memory repository, injected clock, and tests that coordinate two writers with a
  barrier rather than sleeps.
- The broken implementation aliases mutable instruction lists and performs the version
  check after saving.
- Grading verifies stale-writer rejection, immutable nested content, scheduled boundary
  behavior, legal transitions, and history-preserving rollback.

### Interview signal

The candidate should separate lifecycle policy from revision persistence and make the
compare-and-append operation atomic. Copying only the outer object or destructively
restoring an old row does not preserve a trustworthy operational record.

---

## Q12. `digest-scheduler`

**Type:** Concurrency
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A fleet of workers sends scheduled account digests from a shared store. Under load two
workers sometimes send the same digest, while a worker crash can leave a digest stuck
forever. A slow worker may also finish after its lease was reassigned and overwrite the
new owner's result.

Make claims and completion safe under races while preserving parallel work across
different digests.

### Required behavior

- Claiming due work and recording its owner, deadline, and fencing generation is one
  atomic operation.
- Expired work becomes claimable with a strictly newer generation.
- Heartbeats and completion succeed only for the current, unexpired owner/generation.
- A stale worker cannot send or commit after reassignment.
- Retrying a completed digest has no second delivery effect.
- Lifecycle transitions remain explicit and auditable.

### Repository and grading contract

- Shared in-memory transactional store, fake clock, delivery sink, and deterministic
  barriers for claim, expiry, and completion races.
- Tests cover many workers claiming one item, crash recovery, expiry during execution,
  stale completion, and independent jobs progressing concurrently.
- The intended model is leased at-least-once work plus an idempotent/fenced effect, not
  an unsupported promise of magical exactly-once execution.

### Interview signal

Strong solutions treat the fencing generation as proof checked at every state-changing
effect, not merely metadata written during claim.

---

## Q13. `profile-search-projector`

**Type:** Database Engineering
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A profile service writes authoritative rows and an append-only change journal. A search
projector processes journal IDs in batches. In production, a slow transaction reserves
an earlier journal ID but commits after a faster transaction; the projector advances
past the invisible entry and permanently misses the profile change. Deletes and replay
after crashes also diverge from the source of truth.

Repair the SQLite simulation of the projection protocol.

### Required behavior

- Never advance a durable checkpoint across a change that may still become visible.
- Apply creates, updates, and tombstones idempotently.
- Commit projection writes and checkpoint advancement atomically.
- Replaying a processed batch converges without duplicate documents.
- Multiple projectors cannot both publish conflicting checkpoint state.
- Respect the requested batch bound.

### Repository and grading contract

- SQLite tables model profiles, transaction visibility, journal entries, projection,
  and projector ownership without requiring PostgreSQL.
- Deterministic fixtures model allocation order differing from visibility order, a
  crash before checkpoint commit, deletes, repeated profile changes, and two projectors.
- The solution must establish an explicit safe watermark; treating an allocated integer
  as commit order fails hidden tests.

### Interview signal

The key distinction is between identifier order and transaction visibility. The
candidate should restore a replay-safe projection protocol, not patch one missing row.

---

## Q14. `notification-dispatch-node`

**Type:** Architecture Extension
**Difficulty:** Medium
**Timebox:** 30 minutes
**Language:** JavaScript / Node.js

### Candidate question

A working FIFO notification queue needs scheduled delivery and urgency levels. Extend
the Node service without changing its existing FIFO behavior or relying on wall-clock
time.

### Required behavior

- `take(now)` never returns a notification whose `deliverAt` is in the future.
- Among eligible notifications, higher urgency wins; equal urgency preserves insertion
  order.
- A future urgent item never blocks a ready normal item.
- If nothing is eligible, return the existing empty signal even when future work exists.
- Pending size includes both ready and future notifications.
- The exact `now === deliverAt` boundary is eligible.

### Repository and grading contract

- Dependency-free Node repository using `node:test` and an injected timestamp.
- The existing FIFO implementation and tests already pass; the candidate adds a small
  scheduling module under a `creatable` source prefix and wires it into the queue.
- Tests pin stable ties, ready-vs-future ordering, empty-vs-pending semantics, and
  preservation of plain FIFO behavior.

### Interview signal

The candidate should filter by eligibility before ranking and use a stable sequence as
the final comparison key. Sorting the whole queue by urgency first is subtly wrong.

---

## Q15. `device-command-webhook`

**Type:** API Contract Debugging
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

An IoT control API receives at-least-once command-result webhooks. Results for each
device carry a sequence number, but retries and network reordering mean sequence 12 may
arrive before 11. The current endpoint applies duplicates twice and lets future results
overwrite device state before their predecessors are known.

Restore the published acknowledgement and ordering contract.

### Required behavior

- Deduplicate globally by delivery ID without repeating a state transition.
- Apply results strictly by sequence within each device, independently across devices.
- A future result is durably deferred and drained when its gap closes.
- A stale result is acknowledged but cannot mutate state.
- A batch that closes several gaps drains all newly contiguous results deterministically.
- Validation errors remain distinct from accepted duplicate/stale acknowledgements.

### Repository and grading contract

- Small FastAPI endpoint, in-memory transactional store, and tests using ASGI transport.
- Hidden cases include repeated delivery IDs with altered payloads, interleaved devices,
  multiple deferred results, and replay of the complete stream.
- State, dedupe record, and deferred queue updates must be atomic from the handler's
  perspective.

### Interview signal

Idempotency and ordering are separate invariants. A set of IDs alone does not repair
sequence gaps, and a per-device cursor alone does not prevent duplicate effects.

---

## Q16. `enrichment-timeout-incident`

**Type:** Incident Debugging
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

Search requests enrich results with optional catalog labels. After the enrichment
service begins stalling, request latency grows until every worker slot is occupied and
health checks fail. The incident log shows successful responses taking minutes, which
points to an unbounded optional dependency call.

Use the evidence to bound the call and degrade gracefully without weakening genuine
capacity-based load shedding.

### Required behavior

- Healthy and acceptably slow enrichment still returns live labels.
- Calls exceeding the injected 750 ms budget stop at the deadline and return base
  results marked `enrichment: unavailable`.
- Timeout recovery always releases the in-flight slot.
- A burst of stalled enrichment calls does not accumulate permanent saturation.
- Requests arriving when capacity is genuinely full still receive the established 503.
- Deadline equality is defined and tested.

### Repository and evidence

- Read-only incident log, saturation snapshot, runbook, fake clock, and deterministic
  downstream client; no HTTP server, threads, sleeps, or network.
- The broken handler passes no deadline and translates all dependency exceptions into
  500 responses.

### Interview signal

The candidate should diagnose before editing, treat a timeout as a latency budget, and
preserve the distinction between optional-feature degradation and real overload.

---

## Q17. `audit-archive-stream`

**Type:** Runtime Diagnostics
**Difficulty:** Hard
**Timebox:** 35 minutes

### Candidate question

An audit archiver reads database rows, formats newline-delimited records, and uploads
fixed-size chunks. A heap snapshot taken at the first upload shows the entire query and
every formatted record retained, even though the configured chunk size is 128.

Fix the retention spike without changing output bytes or using temporary files.

### Required behavior

- Traverse the one-shot result iterator once and in source order.
- Retain at most one configured chunk of source/formatted records.
- Upload every row exactly once, including a final partial chunk.
- Empty input creates no upload calls.
- A sink failure stops consumption promptly and does not pull the remaining iterator.
- Peak retained records remain bounded as total input grows.

### Repository and evidence

- Read-only heap summary and allocation trace plus instrumented iterator and upload sink.
- Tests compare exact emitted bytes and measure maximum live tracked objects for small
  and large inputs.
- The broken code calls `list()` before chunking; manual garbage collection or a larger
  heap is not an accepted repair.

### Interview signal

The candidate should identify workload-shaped retention rather than a permanent leak
and repair object lifetime through incremental traversal.

---

## Q18. `thumbnail-handoff`

**Type:** Runtime Diagnostics
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

Image-parser threads hand thumbnail tasks to worker threads through a condition-backed
queue. Thread evidence shows workers parked after shutdown, and rare runs lose a worker
when a notification occurs between checking the queue and waiting.

Repair the queue so delivery and shutdown are correct under every interleaving.

### Required behavior

- Queue state, closure, and waiting share the same synchronization boundary.
- Consumers wait in a predicate loop and tolerate spurious wakeups.
- Every accepted task is returned exactly once.
- Closing wakes every parked consumer; workers exit only after accepted work drains.
- Submission after closure is rejected deterministically.
- Shutdown joins all workers without polling or arbitrary sleeps.

### Repository and evidence

- Read-only thread dump and queue counters, a small `Condition`-based queue, and barrier-
  controlled tests that force notify-before-wait, many parked consumers, and close races.
- The broken implementation treats notifications as remembered permits and uses a
  single wakeup for terminal state.

### Interview signal

The important idea is that the predicate is durable state while a notification is only
a hint. Correct shutdown normally requires broadcasting closure and rechecking in a loop.

---

## Q19. `vendor-catalog-reconcile`

**Type:** Repository Implementation
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

An enterprise procurement adapter imports product rows from distributor feeds,
spreadsheets, and an internal catalog. Configured mappings sometimes discard valid tax
codes, while the same item arriving under several vendor identifiers becomes duplicate
canonical products. Later stale rows can also overwrite newer descriptions.

Repair mapping and reconciliation while retaining provenance.

### Required behavior

- Apply each source's configured field map into one canonical product shape.
- Reject only rows without any usable identity key.
- Reconcile products through an explicit identity rule, not incidental field order.
- Preserve every vendor/source identifier across merges.
- Resolve conflicting fields by source timestamp, with deterministic tie-breaking.
- Replaying an import is idempotent and produces a stable output order.

### Repository and grading contract

- Mapping registry, canonical repository, deterministic feed fixtures, and no external
  data libraries.
- Tests separate mapping loss, identity matching, merge precedence, provenance, invalid
  rows, replay, and transitive matches across three feeds.
- Mapping and reconciliation should remain independently testable stages.

### Interview signal

Strong candidates make identity and conflict policy explicit. A single convenient
dictionary key or last-write-wins loop will silently lose business data.

---

## Q20. `lab-sample-history`

**Type:** Database Engineering
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A multi-tenant laboratory stores revised sample observations and reconstructs status
transitions at an ingestion cutoff. The SQL report looks plausible until two tenants
reuse sample IDs or several aliquots advance together: window functions merge unrelated
histories, and corrected revisions appear as new physical observations.

Repair the SQL-backed report without changing fixtures or expected schema.

### Required behavior

- Select the newest revision of each physical observation visible at the cutoff.
- Keep tenant, sample, and aliquot identity in every window partition.
- Collapse only consecutive duplicate statuses within one physical history.
- Preserve real transitions when multiple aliquots share timestamps.
- Treat revision identity separately from mutable payload fields.
- Produce deterministic transition ordinals and previous-status metadata.

### Repository and grading contract

- SQLite schema, seeded collisions/corrections, and a Python report wrapper containing
  the broken CTE/window query.
- Hidden cases cover tenant ID collisions, simultaneous aliquots, payload corrections,
  cutoff equality, duplicate observations, and stable ordering.
- Fixing one fixture with post-query filtering fails; isolation must be correct inside
  the SQL partitions and revision selection.

### Interview signal

The candidate should derive the full business identity before writing window clauses
and recognize that revision keys are not interchangeable with corrected payload values.

---

## Q21. `csv-import`

**Type:** Incident Debugging
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

An overnight customer migration repeatedly crashes on one malformed row, while a
spreadsheet export with a UTF-8 BOM appears to have no identifier column. Restore the
import without silently accepting an invalid file.

### Required behavior and grading contract

- Decode valid UTF-8 with or without a BOM; reject invalid encoding at file scope.
- Require `external_id`, `email`, and `age` headers.
- Quarantine invalid data rows with source row numbers and stable reasons, then continue.
- Normalize valid records and preserve their source order.
- Tests distinguish schema failures from recoverable row failures.

### Interview signal

Strong candidates define the blast-radius boundary: a corrupt schema invalidates the
file, while a bad value invalidates only the row.

---

## Q22. `auth-tenant-leak`

**Type:** API Contract Debugging
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

An authenticated support API scopes collection results but fetches direct ticket IDs
globally. An ID-only cache preserves the leak, and viewers can mutate tickets.

### Required behavior and grading contract

- Scope lookup and mutation by the verified tenant at the store boundary.
- Include tenant identity in cache keys.
- Allow viewers and agents to read, but only agents to rename.
- Make foreign and missing tickets outwardly indistinguishable.
- Verify that a legitimately warmed cache cannot replay data into another tenant.

### Interview signal

The candidate should recognize that data-access queries and caches participate in
authorization; authentication at the route boundary is insufficient.

---

## Q23. `retry-storm`

**Type:** Incident Debugging
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

A webhook client retries every failure immediately, tripling traffic during a partner
outage and retrying permanent request errors.

### Required behavior and grading contract

- Retry only the contract's transient 429 and 503 responses.
- Honor valid `Retry-After`; otherwise use capped exponential delays.
- Count the initial call inside the attempt budget and never sleep after the last call.
- Surface permanent rejection separately from exhausted transient attempts.
- Use an injected fake sleeper so the suite remains deterministic.

### Interview signal

Strong candidates treat retries as load control, classify errors deliberately, and
spot off-by-one calls that violate a stated attempt budget.

---

## Q24. `feature-flag-ext`

**Type:** Architecture Extension
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

Add a runtime client around a working remote flag source. The application should avoid
fetching on every evaluation without turning a control-plane outage into an application
outage.

### Required behavior and grading contract

- Cache immutable snapshots independently per environment for an injected-clock TTL.
- Replace a cached snapshot only after a complete successful fetch.
- Use last-known-good data after refresh failure, but surface cold-start failure.
- Preserve explicit defaults for missing flags and reject invalid TTL configuration.
- Avoid threads, real clocks, and sleeps.

### Interview signal

The candidate should make freshness and failure policy explicit rather than hiding all
source errors or sharing mutable configuration across environments.

---

## Q25. `gc-churn`

**Type:** Runtime Diagnostics
**Difficulty:** Medium
**Timebox:** 30 minutes

### Candidate question

An activity endpoint returns 50 rows but renders hundreds of thousands of historical
events before sorting and slicing. Allocation profiles show GC dominating request CPU.

### Required behavior and grading contract

- Select the newest K events from a one-pass iterable with deterministic ID tie-breaking.
- Bound expensive rendering calls to K rather than total history size.
- Avoid consuming the source for a zero limit and reject a negative limit.
- Preserve the exact newest-first response.

### Interview signal

Strong candidates optimize the expensive allocation boundary, not merely the final
list, and can explain why database-side keyset limiting would be the production ideal.

---

## Q26. `cdc-slot`

**Type:** Database Engineering
**Difficulty:** Hard
**Timebox:** 40 minutes

### Candidate question

A simulated change log serves independent search and analytics slots. Progress from the
fast consumer compacts records still needed by the slow consumer, and arbitrary future
acknowledgements create permanent gaps.

### Required behavior and grading contract

- Track delivered and acknowledged sequence positions independently per slot.
- Reject backwards acknowledgements and positions beyond the delivered range.
- Compact only through the minimum acknowledgement across active slots.
- Allow an explicitly dropped slot to release its retention claim.
- Preserve ordered, resumable polling and reject invalid slot operations.

### Interview signal

The candidate should separate delivery from acknowledgement and derive retention from
the slowest durable consumer rather than the most advanced one.

---

## Research basis

These sources establish the underlying engineering behavior. They are not sources for
candidate-facing wording or repository implementation.

- [Machine Coding, LLD, FDE & Production-Incident Interview Problems](https://github.com/sasrivas25/machine-coding-lld-interview-problems)
  supplied the 100-problem theme map used to identify missing interview muscles.
- The collection's statements on
  [optimistic versioning](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/cms-article-publishing-and-versioning-workflow.md),
  [scheduler leases](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/job-scheduler.md),
  [CDC projection](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/cdc-search-index-synchronization.md), and
  [delayed priority work](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/job-queue-delayed-and-priority-extension.md)
  were used only to extract general invariants; Q11–Q14 use original domains and grading combinations.
- The collection's statements on
  [webhook ordering](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/webhook-event-idempotency-and-ordering.md),
  [downstream deadlines](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/incident-missing-timeout-hang-debugging.md),
  [bounded-memory streaming](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/full-result-materialization-heap-spike.md),
  [condition-variable wakeups](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/missed-signal-lost-wakeup-queue.md),
  [schema reconciliation](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/customer-data-schema-mapping-ingestion.md), and
  [window isolation](https://github.com/sasrivas25/machine-coding-lld-interview-problems/blob/main/problems/sql-window-function-partition-bug.md)
  informed the engineering themes behind Q15–Q20 without reusing their prose, fixtures, or code.
- [OWASP API1:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
  requires object-level authorization checks wherever caller-controlled identifiers
  select resources.
- [RFC 9110 — HTTP Semantics](https://datatracker.ietf.org/doc/html/rfc9110)
  defines the relevant `401`, `403`, and `404` response semantics.
- [RabbitMQ consumer acknowledgements](https://www.rabbitmq.com/docs/confirms)
  documents redelivery after unacknowledged processing and the resulting need for
  idempotent consumers.
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
  documents bounded receive attempts and isolating messages that cannot be processed.
- [OpenFeature evaluation context](https://openfeature.dev/specification/sections/evaluation-context/)
  defines stable targeting keys used for rules and fractional evaluation.
- [PostgreSQL `ALTER TABLE`](https://www.postgresql.org/docs/current/sql-altertable.html)
  documents locking and rewrite implications that motivate staged, bounded migration
  work.
- [PostgreSQL client connection settings](https://www.postgresql.org/docs/current/runtime-config-client.html)
  documents the operational cost of sessions left idle in transactions.
- [Amazon RDS read-replica monitoring](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.Monitoring.html)
  documents asynchronous replica progress and observable replication lag.
- [Python weak references](https://docs.python.org/3/library/weakref.html)
  documents reachability, weak references, and one-shot cleanup finalizers.
- [Amazon S3 multipart uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html)
  documents independently uploaded parts, ordered assembly, checksums, listing, and
  explicit completion or abort.
- [AWS Step Functions state machines](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-statemachines.html)
  documents explicit transitions and terminal states.

## Authoring gate

Before any specification becomes live content:

1. Write a new domain-specific repository from scratch; do not translate or paraphrase
   another challenge's source code.
2. Add two or three passing tests for behavior the candidate must preserve.
3. Add focused failing tests for the stated defect and hidden edge cases above.
4. Keep tests and evidence read-only; use `creatable` only for extension challenges.
5. Write an original `SOLUTION.md` explaining evidence, invariants, fix, alternatives,
   and interview discussion points.
6. Verify the pristine repository fails for the intended reason and the solution
   overlay passes with `scripts/validate_challenges.py`.
7. Review the final brief against this specification and the live catalog for
   accidental duplication before publishing.
