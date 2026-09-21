# MakeItGreen — Challenge Content Backlog

**Audience:** an agent (or engineer) authoring new interview challenges with no prior context.
Read `README.md` for architecture and the authoring recipe. Read `GAPS.md` for platform gaps.
This document is the **content roadmap** — researched challenge ideas, interview mapping, and
authoring conventions.

**Last updated:** 2026-08-31

Three researched, original candidate-question batches are specified in
[`QUESTION_BANK.md`](QUESTION_BANK.md). All 26 entries are now live in the catalog.

---

## Current catalog (49 challenges)

| Order | Slug | Type | Difficulty | Minutes | Core skill |
|------:|------|------|------------|--------:|------------|
| 1 | `orders-service` | Concurrency | Medium | 40 | Atomic stock, retry-safe checkout, recovery, and cancellation |
| 2 | `wallet-service` | Repository Implementation | Easy | 20 | Read tests-as-spec; overdraft + minimum fee bugs |
| 3 | `ledger-api` | API Contract Debugging | Medium | 30 | Wrong status codes, 500 on missing entry, idempotency |
| 4 | `incident-alerts` | Incident Debugging | Medium | 30 | Logs → alerting root cause (timestamps + window) |
| 5 | `booking-db` | Database Engineering | Medium | 30 | SQLite race, cancel forgets inventory, missing UNIQUE |
| 6 | `webhook-ext` | Architecture Extension | Medium | 30 | New `webhooks/` package, HMAC, retry, wire EventBus |
| 7 | `report-latency` | Runtime Diagnostics | Medium | 30 | Profiler evidence → Θ(n²) nested scans |
| 8 | `transfer-deadlock` | Concurrency | Medium | 30 | Opposite-direction lock ordering deadlock |
| 9 | `log-aggregator` | Repository Implementation | Medium | 30 | ERROR rollups over an inclusive sliding window |
| 10 | `pagination-api` | API Contract Debugging | Medium | 25 | Stable opaque keyset pagination under inserts |
| 11 | `deploy-crash` | Incident Debugging | Medium | 30 | Deployment evidence → stale boot configuration |
| 12 | `outbox-publish` | Database Engineering | Hard | 35 | Atomic outbox writes and retry-safe publishing |
| 13 | `cache-ext` | Architecture Extension | Medium | 30 | Injected-clock TTL caching and invalidation |
| 14 | `thread-stall` | Runtime Diagnostics | Medium | 30 | Thread-pool starvation from nested submissions |
| 15 | `metrics-rollups` | Repository Implementation | Medium | 30 | Time buckets, late data, bounded cardinality |
| 16 | `rate-limiter` | Concurrency | Medium | 25 | Atomic per-tenant sliding-window admission |
| 17 | `topk-errors` | Runtime Diagnostics | Hard | 35 | Bounded approximate heavy hitters |
| 18 | `return-workflow` | Repository Implementation | Easy | 20 | Explicit lifecycle transitions and atomic rejection |
| 19 | `project-vault-api` | API Contract Debugging | Medium | 30 | Tenant-scoped document authorization and role capabilities |
| 20 | `audit-export-pool` | Database Engineering | Medium | 30 | Connection release and transaction cleanup on every path |
| 21 | `device-ingest-incident` | Incident Debugging | Medium | 30 | Per-event poison isolation with classified quarantine |
| 22 | `invoice-delivery-worker` | Concurrency | Hard | 40 | Idempotent delivery, safe acknowledgement, and scheduled retries |
| 23 | `release-gates` | Architecture Extension | Hard | 40 | Deterministic targeting precedence and stable rollout cohorts |
| 24 | `invoice-cents-migration` | Database Engineering | Hard | 40 | Online dual writes, keyset backfill, and verified completion |
| 25 | `workspace-replica-router` | Database Engineering | Hard | 40 | Session read-your-writes across lagging replicas |
| 26 | `build-stream-leak` | Runtime Diagnostics | Hard | 40 | Callback retention, lifecycle cleanup, and publish/close races |
| 27 | `artifact-upload-ext` | Architecture Extension | Hard | 45 | Resumable chunks, integrity checks, terminal state, and deduplication |
| 28 | `subscription-renew` | Repository Implementation | Hard | 45 | Multi-bug billing boundary, pricing, retry, and decline atomicity |
| 29 | `webhook-batch-node` | Repository Implementation | Medium | 30 | Tenant-isolated Node.js batching and retry-safe delivery |
| 30 | `runbook-revisions` | Repository Implementation | Medium | 30 | Optimistic revisions, immutable history, and append-only rollback |
| 31 | `digest-scheduler` | Concurrency | Hard | 40 | Atomic leased claims and stale-owner fencing |
| 32 | `profile-search-projector` | Database Engineering | Hard | 40 | Visibility-safe CDC checkpointing and atomic projection |
| 33 | `notification-dispatch-node` | Architecture Extension | Medium | 30 | Due-before-priority stable notification dispatch |
| 34 | `device-command-webhook` | API Contract Debugging | Hard | 40 | Delivery dedupe and per-device ordered application |
| 35 | `enrichment-timeout-incident` | Incident Debugging | Medium | 30 | Downstream deadline budget and optional-feature fallback |
| 36 | `audit-archive-stream` | Runtime Diagnostics | Hard | 35 | One-pass bounded-memory export and prompt failure stop |
| 37 | `thumbnail-handoff` | Runtime Diagnostics | Hard | 40 | Predicate-based condition waiting and broadcast shutdown |
| 38 | `vendor-catalog-reconcile` | Repository Implementation | Hard | 40 | Explicit identity, provenance, and recency-aware merges |
| 39 | `lab-sample-history` | Database Engineering | Hard | 40 | Full-identity SQL window partitioning and revision selection |
| 40 | `csv-import` | Incident Debugging | Medium | 30 | File-level schema errors versus row-level quarantine |
| 41 | `auth-tenant-leak` | API Contract Debugging | Medium | 30 | Tenant-scoped lookup, cache keys, and mutation capabilities |
| 42 | `retry-storm` | Incident Debugging | Medium | 30 | Retry classification, backpressure, and attempt budgets |
| 43 | `feature-flag-ext` | Architecture Extension | Medium | 30 | Environment-scoped last-known-good flag snapshots |
| 44 | `gc-churn` | Runtime Diagnostics | Medium | 30 | Bounded top-K selection before expensive rendering |
| 45 | `cdc-slot` | Database Engineering | Hard | 40 | Slowest-slot retention and acknowledgement fencing |
| 46 | `token-auth-api` | API Contract Debugging | Easy | 20 | Exact bearer-token and capability matching |
| 47 | `config-merge` | Repository Implementation | Easy | 20 | Preserve explicit false, zero, and empty overrides |
| 48 | `job-lease` | Concurrency | Medium | 30 | Expiry and generation fencing for worker leases |
| 49 | `queue-drain` | Incident Debugging | Medium | 30 | Quarantine poison events without stranding healthy work |

**Status:** all 49 pass `scripts/validate_challenges.py` (pristine `repo/` fails; `repo/` + `solution/` passes).

## Fourth authoring batch (orders 46–49) — COMPLETE

| Order | Slug | Type | Difficulty | Primary invariant |
|---:|---|---|---|---|
| 46 | `token-auth-api` | API Contract Debugging | Easy | Exact credentials and capability boundaries — ✅ live |
| 47 | `config-merge` | Repository Implementation | Easy | Presence beats truthiness for explicit overrides — ✅ live |
| 48 | `job-lease` | Concurrency | Medium | Lease generations fence stale workers — ✅ live |
| 49 | `queue-drain` | Incident Debugging | Medium | Poison messages do not stop healthy work — ✅ live |

Curated learning paths and a difficulty ladder live in [`PREP_TRACKS.md`](PREP_TRACKS.md).
The publishing gates and weekly rotation live in [`CONTENT_CADENCE.md`](CONTENT_CADENCE.md).
The Node runner contract and live challenges are documented in
[`SECOND_LANGUAGE_PLAN.md`](SECOND_LANGUAGE_PLAN.md).

---

## Second authoring batch (orders 30–39) — COMPLETE

The second researched batch is fully specified in
[`QUESTION_BANK.md`](QUESTION_BANK.md#second-batch-overview). These are original
MakeItGreen briefs derived from general themes in the external collection, not copied
problem statements.

| Order | Slug | Type | Difficulty | Primary invariant |
|---:|---|---|---|---|
| 30 | `runbook-revisions` | Repository Implementation | Medium | Immutable history + optimistic writes — ✅ live |
| 31 | `digest-scheduler` | Concurrency | Hard | Lease fencing and stale-owner rejection — ✅ live |
| 32 | `profile-search-projector` | Database Engineering | Hard | Visibility-safe CDC checkpointing — ✅ live |
| 33 | `notification-dispatch-node` | Architecture Extension | Medium | Due-before-priority stable dispatch — ✅ live |
| 34 | `device-command-webhook` | API Contract Debugging | Hard | Delivery dedupe + per-device ordering — ✅ live |
| 35 | `enrichment-timeout-incident` | Incident Debugging | Medium | Deadline budget and graceful degradation — ✅ live |
| 36 | `audit-archive-stream` | Runtime Diagnostics | Hard | One-pass bounded-memory export — ✅ live |
| 37 | `thumbnail-handoff` | Runtime Diagnostics | Hard | Predicate-based waiting and clean shutdown — ✅ live |
| 38 | `vendor-catalog-reconcile` | Repository Implementation | Hard | Explicit identity, provenance, merge precedence — ✅ live |
| 39 | `lab-sample-history` | Database Engineering | Hard | Full-identity SQL window partitioning — ✅ live |

The complete batch spans all seven challenge types and includes the catalog's second
Node repository.

---

## Third authoring batch (orders 40–45) — COMPLETE

| Order | Slug | Type | Difficulty | Primary invariant |
|---:|---|---|---|---|
| 40 | `csv-import` | Incident Debugging | Medium | Quarantine bad rows without accepting malformed files — ✅ live |
| 41 | `auth-tenant-leak` | API Contract Debugging | Medium | Tenant identity belongs in lookup and cache boundaries — ✅ live |
| 42 | `retry-storm` | Incident Debugging | Medium | Retry only transient failures with bounded delay and attempts — ✅ live |
| 43 | `feature-flag-ext` | Architecture Extension | Medium | Preserve environment-scoped last-known-good snapshots — ✅ live |
| 44 | `gc-churn` | Runtime Diagnostics | Medium | Bound expensive allocations to the response limit — ✅ live |
| 45 | `cdc-slot` | Database Engineering | Hard | Compact only through the slowest active acknowledgement — ✅ live |

The third batch converts the former Tier 3 ideas into distinct repositories. Future
content should begin as a separately researched fourth batch rather than extending the
completed tracker below.

---

## Research sources

| Source | What it covers |
|--------|----------------|
| [Machine-coding problem collection](https://github.com/sasrivas25/machine-coding-lld-interview-problems) | 100 statement-only themes across LLD, concurrency, database, incidents, runtime, integrations, data/ML, and Linux |
| Datadog interview guides (2025–2026) | Log parsers, metrics aggregators, rate limiters, thread-safe structures, LRU+TTL, streaming top-K |
| Stripe Bug Squash / Retool debugging | Unfamiliar repo, failing tests, process graded over speed; single- vs multi-bug |
| Database interview patterns | PostgreSQL transactions, indexes, migrations, replication, partitioning, CDC, outbox |
| Runtime-diagnostics patterns | Heap evidence, thread dumps, GC logs — retention, deadlocks, starvation, allocation churn |

---

## Gap vs. real interviews

| Interview format | Covered today? | Best new challenge |
|------------------|----------------|-------------------|
| Stripe Bug Squash (navigate unfamiliar repo) | Yes (45 varied repositories) | Continue domain diversity |
| Retool multi-bug failing tests | Yes (`subscription-renew`, `vendor-catalog-reconcile`) | Research a third multi-bug scenario |
| Datadog log parser / aggregator | Partial → **`log-aggregator`** | `log-aggregator`, `metrics-rollups` |
| Datadog rate limiter / thread-safe DS | Yes (`rate-limiter`, `transfer-deadlock`, `thumbnail-handoff`) | Continue multi-language depth |
| Heap/thread/GC diagnostics | Yes (`report-latency`, `thread-stall`, `build-stream-leak`, `audit-archive-stream`, `thumbnail-handoff`, `gc-churn`) | Research a GC-log or native-runtime scenario next |
| DB outbox/replication/migrations | Yes, including CDC projection and SQL window isolation | Continue database depth |
| Machine coding “extend the service” | Yes, including two Node repositories | Continue multi-language depth |

---

## Tier 1 — Highest-value additions

Strong interview realism + good fit for MakeItGreen's repo/pytest format.

### `transfer-deadlock` — Concurrency (Medium, 30 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Two accounts; concurrent transfers in opposite directions deadlock |
| **Bug** | Locks acquired in transfer direction (`src` then `dst`) instead of consistent global order |
| **Fix** | Lock accounts in sorted ID order (e.g. `min(src,dst)` first) |
| **Why** | Complements `orders-service` (oversell race) with **lock ordering** — classic bank-transfer interview |
| **Tests** | Opposite-direction concurrent transfers must complete; balances stay correct; no thread hang |

### `pagination-api` — API Contract Debugging (Medium, 25 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Cursor pagination returns duplicates when rows inserted mid-scroll |
| **Bug** | `OFFSET/LIMIT` without stable cursor; or broken `next_cursor` encoding |
| **Why** | Stripe/GitHub-style contract debugging; natural follow-up to `ledger-api` idempotency |
| **Tests** | Contract tests for cursor stability under concurrent inserts |

### `deploy-crash` — Incident Debugging (Medium, 30 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Service won't start after deploy; tests won't even run |
| **Bug** | Wrong env default, renamed module with stale import, circular import |
| **Why** | Different muscle than `incident-alerts` (runtime SLO miss) — starts with "can't boot" |
| **Evidence** | Readonly `logs/deploy-failure.log`, `logs/startup-traceback.txt` |
| **readonly** | `["tests/", "logs/"]` |

### `outbox-publish` — Database Engineering (Hard, 35 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Orders save but events never fire; duplicate events on retry |
| **Bug** | Outbox row not in same transaction; publisher doesn't mark `published_at`; no dedupe |
| **Why** | Outbox and CDC are production-relevant distributed-systems patterns |
| **Note** | SQLite + fake in-process publisher in tests (no Kafka) |

### `cache-ext` — Architecture Extension (Medium, 30 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Working read API; add TTL cache with correct invalidation |
| **Your job** | New `cache/` package, wire into repository |
| **creatable** | `["cache/"]` |
| **Why** | Pairs with `webhook-ext` but tests read-path extension |

### `thread-stall` — Runtime Diagnostics (Medium, 30 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | API stops accepting requests; CPU ~0% |
| **Bug** | Deadlock or connection pool exhaustion |
| **Evidence** | Readonly `diagnostics/threads.txt`, `diagnostics/sre-notes.md` |
| **Why** | Complements profiler-based diagnosis with thread-dump analysis |

---

## Tier 2 — Datadog-flavored

Mirror CoderPad "applied data processing" rounds; frame as fix/extend a broken component.

### `log-aggregator` — Repository Implementation (Medium, 30 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Parse structured log lines; count ERRORs per service in a sliding time window |
| **Bugs** | Counts non-ERROR levels; window start boundary off-by-one (exclusive vs inclusive) |
| **Datadog tie-in** | Log parser with state; sliding-window aggregation |
| **Log format** | `2026-08-29T03:10:00Z ERROR checkout-api payment declined` |

### `metrics-rollups` — Repository Implementation (Medium, 30 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Ingest `(metric, value, timestamp)`; return min/max/avg/count per metric for last N minutes |
| **Bugs** | Wrong bucket alignment; late-arriving points dropped; cardinality explosion |
| **Datadog tie-in** | Streaming aggregator / time-series rollup |

### `rate-limiter` — Concurrency (Medium, 25 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Token-bucket or sliding-window limiter under multi-threaded load |
| **Bugs** | Race on token refill; burst math wrong; per-tenant isolation broken |
| **Datadog tie-in** | Explicit in interview guides; real agent code has rate limiter patterns |

### `topk-errors` — Runtime Diagnostics (Hard, 35 min) ✅ IMPLEMENTED

| Field | Value |
|-------|-------|
| **Pattern** | Top-K services by error count from a large stream with bounded memory |
| **Bug** | Unbounded `dict`; fix with heap or count-min sketch |
| **Datadog tie-in** | Cardinality-bounded top-K |

---

## Tier 3 — Additional formats — COMPLETE

| Slug | Type | Theme | Effort |
|------|------|-------|--------|
| `subscription-renew` | Repository Implementation | Renewal + proration from test spec | ✅ |
| `csv-import` | Incident Debugging | Broken import (encoding, schema, row quarantine) | ✅ |
| `auth-tenant-leak` | API Contract Debugging | Direct lookup and cache cross tenant boundaries | ✅ |
| `retry-storm` | Incident Debugging | Immediate retries amplify a partner outage | ✅ |
| `feature-flag-ext` | Architecture Extension | Last-known-good snapshot client | ✅ |
| `gc-churn` | Runtime Diagnostics | Unbounded response rendering drives allocation churn | ✅ |
| `cdc-slot` | Database Engineering | Multi-consumer CDC retention and acknowledgement | ✅ |

**Still optional for future coverage:** another language beyond Python/JavaScript.
System-design diagram exercises are intentionally out of scope. Difficulty tracks,
weekly cadence, prep guides, and JavaScript runtime support are already live.

## Later product ideas

The curated prep tracks are intentionally kept out of the main catalog for now. If
they become product UI later, use a lightweight secondary surface rather than adding
a large chooser to the challenge list.

Later TODOs:

- A secondary prep-track view with descriptions, progress, and a recommended next challenge.
- Retention practice: retry queue, weekly review prompts, and repeated-mistake signals.
- Publishing operations: a visible weekly release workflow and cadence tracking.

---

## Completed authoring batch

**Datadog intern prep sequence:**

1. `transfer-deadlock` ✅
2. `pagination-api` ✅
3. `log-aggregator` ✅
4. `thread-stall` ✅
5. `outbox-publish` ✅

The same batch also completed `cache-ext`, `deploy-crash`, `metrics-rollups`,
`rate-limiter`, and `topk-errors`. The former Tier 3 list is now fully implemented as
orders 28 and 40–45.

---

## Authoring conventions (MUST preserve)

1. **Validation discipline:** broken `repo/` must fail pytest; `repo/` + `solution/` overlay must pass.
   Run `python scripts/validate_challenges.py` from `greenline/`.
2. **Readonly:** `tests/` always readonly. Evidence dirs (`logs/`, `diagnostics/`) readonly when they're the "start here" artifact.
3. **Creatable:** declare only the narrow prefixes where the candidate must add files;
   this is common, but not mandatory, for Architecture Extension challenges.
4. **Dependencies:** prefer the standard library. When external Python packages are
   essential, declare `runtime.requirements` so the platform uses an isolated cached environment.
5. **Brief:** force explore-before-edit ("read `logs/` first", "read `diagnostics/` first").
6. **Passing tests:** include 2–3 green tests encoding unrelated correct behavior so candidates don't break working paths.
7. **SOLUTION.md:** root cause, fix, interview talking points (see existing challenges).
8. **order field:** catalog sort key; assign next integer after highest existing.
9. **minutes:** 20 Easy, 25–30 Medium, 35+ Hard.

### `challenge.json` template

```json
{
  "order": 99,
  "title": "slug-here",
  "type": "Concurrency | Repository Implementation | API Contract Debugging | Incident Debugging | Database Engineering | Architecture Extension | Runtime Diagnostics",
  "difficulty": "Easy | Medium | Hard",
  "minutes": 30,
  "language": "Python",
  "blurb": "One-line catalog teaser.",
  "brief": "Markdown brief shown in workspace.\\n\\n**Your job:** make all tests green.",
  "readonly": ["tests/"]
}
```

Add `"creatable": ["package/"]` only when the candidate must create files.

### Folder layout

```
challenges/<slug>/
├── challenge.json
├── repo/
│   ├── conftest.py
│   ├── README.md          # optional repo context
│   ├── <package>/
│   └── tests/
└── solution/
    ├── SOLUTION.md
    └── <package>/         # fixed files, same relative paths as repo
```

---

## Implementation status tracker

| Slug | Status | Order | Notes |
|------|--------|------:|-------|
| `transfer-deadlock` | ✅ done | 8 | Concurrency — lock ordering |
| `log-aggregator` | ✅ done | 9 | Datadog-flavored log window aggregation |
| `pagination-api` | ✅ done | 10 | API Contract — stable keyset cursor |
| `deploy-crash` | ✅ done | 11 | Incident — stale boot module evidence |
| `outbox-publish` | ✅ done | 12 | Database — atomic outbox + retry semantics |
| `cache-ext` | ✅ done | 13 | Architecture Extension — TTL + invalidation |
| `thread-stall` | ✅ done | 14 | Runtime Diagnostics — pool starvation |
| `metrics-rollups` | ✅ done | 15 | Repository Implementation — bounded rollups |
| `rate-limiter` | ✅ done | 16 | Concurrency — per-tenant atomic admission |
| `topk-errors` | ✅ done | 17 | Runtime Diagnostics — bounded heavy hitters |
| `return-workflow` | ✅ done | 18 | Repository Implementation — explicit return state machine |
| `project-vault-api` | ✅ done | 19 | API Contract — tenant and role authorization |
| `audit-export-pool` | ✅ done | 20 | Database — scoped connection and transaction cleanup |
| `device-ingest-incident` | ✅ done | 21 | Incident — poison-event isolation and quarantine |
| `invoice-delivery-worker` | ✅ done | 22 | Concurrency — idempotent effects and retry scheduling |
| `release-gates` | ✅ done | 23 | Architecture Extension — deterministic rollout evaluation |
| `invoice-cents-migration` | ✅ done | 24 | Database — online expansion and restart-safe keyset backfill |
| `workspace-replica-router` | ✅ done | 25 | Database — monotonic read-your-writes routing |
| `build-stream-leak` | ✅ done | 26 | Runtime Diagnostics — event subscription retention and cleanup |
| `artifact-upload-ext` | ✅ done | 27 | Architecture Extension — resumable content-addressed uploads |
| `subscription-renew` | ✅ done | 28 | Repository Implementation — interacting renewal boundary, pricing, retry, and failure bugs |
| `webhook-batch-node` | ✅ done | 29 | Repository Implementation — first Node.js challenge; isolated retry-safe batches |
| `runbook-revisions` | ✅ done | 30 | Repository Implementation — optimistic revisions and immutable history |
| `notification-dispatch-node` | ✅ done | 33 | Architecture Extension — scheduled stable-priority Node queue |
| `enrichment-timeout-incident` | ✅ done | 35 | Incident Debugging — bounded optional dependency fallback |
| `audit-archive-stream` | ✅ done | 36 | Runtime Diagnostics — bounded streaming retention |
| `digest-scheduler` | ✅ done | 31 | Concurrency — leased claims and fencing generations |
| `profile-search-projector` | ✅ done | 32 | Database — visibility-safe CDC projection |
| `device-command-webhook` | ✅ done | 34 | API Contract — idempotent ordered webhook results |
| `thumbnail-handoff` | ✅ done | 37 | Runtime Diagnostics — condition predicate and broadcast close |
| `vendor-catalog-reconcile` | ✅ done | 38 | Repository Implementation — mapping and identity reconciliation |
| `lab-sample-history` | ✅ done | 39 | Database — tenant-isolated revised window history |
| `csv-import` | ✅ done | 40 | Incident — file schema versus row quarantine |
| `auth-tenant-leak` | ✅ done | 41 | API Contract — tenant-scoped lookup, cache, and mutation |
| `retry-storm` | ✅ done | 42 | Incident — classified, bounded retry behavior |
| `feature-flag-ext` | ✅ done | 43 | Architecture Extension — last-known-good flag snapshots |
| `gc-churn` | ✅ done | 44 | Runtime Diagnostics — bounded rendering allocations |
| `cdc-slot` | ✅ done | 45 | Database — slowest-slot retention and ack fencing |

---

## Agent handoff checklist

When implementing a backlog item:

- [ ] Copy an existing `challenge.json`; set `order`, `type`, `brief`, `readonly`/`creatable`
- [ ] Write `repo/` with intentional bug(s); at least one failing test encodes the spec
- [ ] Include passing tests for unrelated correct behavior
- [ ] Write `solution/` overlay + `SOLUTION.md` with talking points
- [ ] Run `python scripts/validate_challenges.py` — both states must pass
- [ ] Update this file's status tracker
- [ ] Update `README.md` seed challenges table
- [ ] Optionally update `GAPS.md` gap 9 challenge count
