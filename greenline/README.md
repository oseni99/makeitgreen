# MakeItGreen

A local-first clone of [Gronex](https://gronex.org/) — repository-based backend
interview practice. Real repos with failing tests, a browser workspace, a
sandboxed test runner, and reviewed reference solutions.

![status](https://img.shields.io/badge/tests-make%20them%20green-46f28a)

## Architecture

```
greenline/
├── backend/          FastAPI
│   ├── app.py        HTTP API (challenges, files, run, reset, solution)
│   ├── challenges.py challenge discovery + file access (path-traversal safe)
│   ├── runner.py     test sandbox: temp-dir copy + user-edit overlay + pytest with timeout
│   ├── progress.py   SQLite progress store (todo / attempted / solved)
│   └── data/         workspaces (user edits) + progress.db  [gitignore-able]
├── challenges/       content: one folder per challenge
│   └── <slug>/
│       ├── challenge.json   metadata + brief (markdown)
│       ├── repo/            the broken codebase (tests/ are read-only in UI)
│       └── solution/        SOLUTION.md + fixed files
└── frontend/         Vite + React + TypeScript + Tailwind v4 + Monaco
    ├── src/components/ui/  locally owned shadcn-style primitives
    ├── src/styles/         canonical semantic theme and global layers
    └── src/pages/          Landing, Catalog, Workspace, Solution
```

The frontend follows [`DESIGN.md`](DESIGN.md): a warm document-like canvas,
Inter typography, one structural blue accent, restrained elevation, and decorative
sticker colors that never compete with actions. Tailwind utilities are the default;
custom CSS remains only where the editor and specialized content rendering require it.

How a test run works: the runner copies `repo/` into a temp dir, overlays any
files you edited in the browser (stored in `backend/data/workspaces/<slug>/`),
runs the challenge's declared test command with a 60s timeout, parses the counts, and records progress.
Going green marks the challenge solved.

## Run it

```bash
# backend (port 8000)
cd backend
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
set -a; source .env.local; set +a
./venv/bin/uvicorn app:app --port 8000

# frontend (port 5173, proxies /api to 8000)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

Authentication setup is documented in [AUTH.md](AUTH.md). The production
configuration uses Clerk with Google as the sole sign-in provider.

## Seed challenges

| Challenge | Type | What's broken |
|---|---|---|
| `orders-service` | Concurrency | Check-then-act race oversells inventory under concurrent checkouts |
| `wallet-service` | Repository Implementation | Overdraft on transfers + minimum fee never charged |
| `ledger-api` | API Contract Debugging | Wrong status code, 500 on missing entry, ignored Idempotency-Key |
| `incident-alerts` | Incident Debugging | Missed page: naive vs aware timestamps (fail-closed) + exclusive window drops the sample at `now` |
| `booking-db` | Database Engineering | Last-seat race double-books, cancel forgets inventory, missing UNIQUE lets fans book twice |
| `webhook-ext` | Architecture Extension | Add a `webhooks/` package (HMAC-signed POSTs + retry) and wire it into the event bus |
| `report-latency` | Runtime Diagnostics | Profiler shows per-customer full scans; report is correct but Θ(customers·orders) |
| `transfer-deadlock` | Concurrency | Opposite-direction transfers deadlock — locks acquired in transfer order, not global order |
| `log-aggregator` | Repository Implementation | WARN counted as ERROR; sliding window drops events on the start boundary |
| `pagination-api` | API Contract Debugging | OFFSET cursor repeats/skips events after concurrent inserts; ordering lacks a stable tie-breaker |
| `deploy-crash` | Incident Debugging | Renamed configuration module leaves the production default pointing at a missing import |
| `outbox-publish` | Database Engineering | Business/outbox writes split transactions; retries publish duplicate events |
| `cache-ext` | Architecture Extension | Add an injected-clock TTL cache and wire correct save/delete invalidation |
| `thread-stall` | Runtime Diagnostics | Same-pool nested work starves because workers await work the pool cannot schedule |
| `metrics-rollups` | Repository Implementation | Bucket alignment, late-arrival retention, and active-cardinality enforcement are broken |
| `rate-limiter` | Concurrency | Shared tenant state and a check-then-record race exceed the window limit |
| `topk-errors` | Runtime Diagnostics | Exact per-service counters grow without bound; replace them with bounded heavy hitters |
| `return-workflow` | Repository Implementation | Invalid return transitions and rejected actions corrupt lifecycle history |
| `project-vault-api` | API Contract Debugging | Global document lookup and loose role checks cross authorization boundaries |
| `audit-export-pool` | Database Engineering | Failure paths leak pooled connections and unfinished transactions |
| `device-ingest-incident` | Incident Debugging | A poison telemetry event ends the drain loop and strands healthy traffic |
| `invoice-delivery-worker` | Concurrency | Early acknowledgements, duplicate effects, and hot retries violate queue safety |
| `release-gates` | Architecture Extension | Add deterministic targeting, precedence, and stable percentage cohorts |
| `invoice-cents-migration` | Database Engineering | Offset backfill and legacy-only writes make an online money migration unsafe |
| `workspace-replica-router` | Database Engineering | Replica-only reads violate session read-your-writes under replication lag |
| `build-stream-leak` | Runtime Diagnostics | Event-hub callbacks retain closed streams and their bounded histories |
| `artifact-upload-ext` | Architecture Extension | Add persistent resumable uploads with chunk and full-artifact integrity |
| `subscription-renew` | Repository Implementation | Repair interacting boundary, pricing, retry-idempotency, and decline-atomicity bugs |
| `webhook-batch-node` | Repository Implementation | Node.js tenant-isolated batching with exact boundaries and retry-safe delivery |
| `runbook-revisions` | Repository Implementation | Stale writes, illegal lifecycle jumps, schedule boundary, and destructive rollback |
| `notification-dispatch-node` | Architecture Extension | Node.js due-time filtering and stable urgency ordering over a working FIFO queue |
| `enrichment-timeout-incident` | Incident Debugging | Missing optional-dependency deadline exhausts worker capacity instead of degrading |
| `audit-archive-stream` | Runtime Diagnostics | Chunked writes still materialize the complete query and formatted result set |
| `digest-scheduler` | Concurrency | Non-atomic claims and missing fencing let stale lease owners deliver |
| `profile-search-projector` | Database Engineering | Allocated CDC IDs are mistaken for a visibility-safe checkpoint |
| `device-command-webhook` | API Contract Debugging | Delivery retries and per-device sequence gaps corrupt command state |
| `thumbnail-handoff` | Runtime Diagnostics | Spurious wakeups lose consumers and close wakes only one parked worker |
| `vendor-catalog-reconcile` | Repository Implementation | Mapping loss, weak identity matching, and stale merge precedence |
| `lab-sample-history` | Database Engineering | Partial SQL window identities mix tenants, aliquots, and revisions |
| `csv-import` | Incident Debugging | BOM and one malformed row turn a recoverable partner import into a batch restart loop |
| `auth-tenant-leak` | API Contract Debugging | ID-only lookup and cache keys bypass tenant scope and route capabilities |
| `retry-storm` | Incident Debugging | Immediate retries amplify transient failures and repeat permanent rejections |
| `feature-flag-ext` | Architecture Extension | Add environment-scoped last-known-good snapshots with deterministic refresh |
| `gc-churn` | Runtime Diagnostics | Every historical event is rendered before a bounded activity feed is sliced |
| `cdc-slot` | Database Engineering | Fast-consumer progress compacts changes still required by slower CDC slots |
| `token-auth-api` | API Contract Debugging | Exact bearer-token and capability matching |
| `config-merge` | Repository Implementation | Preserve explicit false, zero, and empty overrides |
| `job-lease` | Concurrency | Expiry and generation fencing for worker leases |
| `queue-drain` | Incident Debugging | Quarantine poison events without stranding healthy work |

## Adding a challenge

1. Create `challenges/<slug>/challenge.json` (copy an existing one).
   Useful fields:
   - `order` — catalog sort key (lower first; default `999` if omitted)
   - `readonly` — path prefixes the user cannot edit (default `["tests/"]`)
   - `creatable` — optional prefixes where the user may add new files
     (e.g. `["orders/"]`)
   - `runtime` — optional execution contract. Python is the default; use
     `{"kind":"python","requirements":"requirements.txt"}` for isolated
     dependencies, or an allowlisted command such as
     `{"kind":"node","command":["node","--test"],"report":"text"}`.
   Every `conftest.py` and root pytest config stay read-only regardless.
2. Put the broken repo in `repo/`. Python challenges use a pytest suite (and may use a
   root `conftest.py`); other runtimes use the command declared in `runtime`. In every
   case, the failing tests encode the spec.
3. Put fixed files (same relative paths) + `SOLUTION.md` in `solution/`.
4. Verify both states: the repo must fail, `repo/` + `solution/` overlay must pass
   (`python scripts/validate_challenges.py` from `greenline/`).

New content starts in **[QUESTION_BANK.md](QUESTION_BANK.md)**. It tracks researched,
original candidate questions and their implementation status. New specifications must
become broken repositories, tests, and reviewed solutions before entering the catalog.

Use **[PREP_TRACKS.md](PREP_TRACKS.md)** for curated learning paths and the difficulty
ladder. Challenge authors should follow **[CONTENT_CADENCE.md](CONTENT_CADENCE.md)**;
the Node runtime contract and live exercises are documented in
**[SECOND_LANGUAGE_PLAN.md](SECOND_LANGUAGE_PLAN.md)**.

## Known gaps / backlog

See **[GAPS.md](GAPS.md)** — a detailed, prioritized handoff doc covering every known
gap with file references and suggested implementations. Start there before adding features.

## Notes and limits

- Python and Node challenges are supported through metadata-declared runtime
  commands. Optional Python `requirements.txt` files get content-addressed cached
  environments and are read-only in the workspace; platform dependencies remain
  separate in `backend/requirements.txt`.
- The "sandbox" is a temp dir + timeout — fine for your own machine, not for
  hosting untrusted users. Containerize the runner before ever deploying.
- Clerk Google sign-in is supported when configured; local development without Clerk
  remains available. Authenticated workspace and progress state is isolated per Clerk user.
