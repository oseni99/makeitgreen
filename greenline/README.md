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
│   ├── runner.py     Challenge Run interface + local and container adapters
│   ├── learner_state.py local and PostgreSQL learner-state adapters
│   ├── run_coordination.py PostgreSQL Run Jobs + fenced workers
│   ├── worker.py        Hosted execution-worker entrypoint
│   ├── serve.py         Hosted control-plane entrypoint
│   ├── abuse_controls.py request admission, body/rate limits, audit
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

How a Challenge Run works: the selected execution adapter receives one normalized
request. The Local Mode adapter copies `repo/` into a temp dir, overlays any
files you edited in the browser (stored in `backend/data/workspaces/<slug>/`),
runs the challenge's declared test command with a 60s timeout, parses the counts, and records progress.
Going green marks the challenge solved.

The container adapter supplies the same normalized result while running a
validated, user-scoped Run Bundle in a fresh Docker container. It uses
digest-pinned preloaded images, no network, a read-only root filesystem,
non-root execution, dropped capabilities, no privilege escalation, a read-only
host mount, bounded tmpfs work areas, and CPU/memory/PID/wall-clock limits. See
[`backend/execution-images/README.md`](backend/execution-images/README.md) for
the image contract.

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

For Hosted Mode, run `./venv/bin/python serve.py` for the public control plane
and `./venv/bin/python worker.py` as a separate execution worker. The API
launcher applies the explicit
`GREENLINE_TRUSTED_PROXY_CIDRS` allowlist; Hosted composition rejects a missing
launcher marker, wildcard proxy trust, or missing security-log HMAC key.

`GREENLINE_MODE` is mandatory. Use `local` for the trusted personal workflow.
`hosted` never falls back to host subprocess execution. The public API installs
a disabled execution Adapter and only enqueues durable work; it must not receive
a Docker socket or Docker CLI. The worker is the only process that recognizes
the container execution Adapter. Learner Challenge State stores
workspace overlays, progress, and run history transactionally in PostgreSQL.
Hosted Mode uses PostgreSQL Run Jobs and fenced cross-replica operation leases;
disposable workers cannot commit after their claim is superseded. PostgreSQL
request admission adds per-learner budgets, durable audit events, and global and
per-learner active-run capacity. Oversized bodies are rejected before parsing.
Worker startup verifies the Docker daemon and both immutable execution images.
The API's `/health/ready` checks its PostgreSQL dependencies only, so execution
capacity loss cannot remove the control plane used to observe queued jobs.
`/health/release` applies the same readiness checks and also requires every
fresh worker heartbeat to report the same immutable build commit and execution
image refs. Workers refresh that PostgreSQL heartbeat only after rechecking the
Docker daemon and both images, so promotion automation rejects stale control,
worker, or execution components without exposing a worker HTTP listener.

### Production control-plane image

The root `Dockerfile` builds the Vite frontend and FastAPI backend into one
non-root control-plane image. Base images are deliberately required build args;
pass only references approved and pinned to an OCI index digest:

```bash
docker build \
  --build-arg NODE_BASE='node:22-bookworm-slim@sha256:<approved-index-digest>' \
  --build-arg PYTHON_BASE='python:3.13-slim-bookworm@sha256:<approved-index-digest>' \
  --build-arg SOURCE_REVISION='<full-40-character-commit-sha>' \
  --build-arg VITE_CLERK_PUBLISHABLE_KEY='pk_live_...' \
  --target control-plane \
  -t greenline-control-plane .
```

Run it with a read-only root filesystem, all capabilities dropped, and a small
temporary filesystem if the platform requires `/tmp`. Do not mount the Docker
socket into this container. Deliver Clerk, database, and log-HMAC secrets by
mounted files and set the trusted proxy CIDRs at deployment time.

### Production execution-worker image

`Dockerfile.worker` builds a separate numeric non-root image containing the
worker, PostgreSQL driver, challenge catalog, and Docker CLI—but no HTTP server,
Clerk SDK, or frontend. Both bases must be compatible Linux images pinned to
approved OCI index digests:

```bash
docker build -f Dockerfile.worker \
  --build-arg PYTHON_BASE='python:3.13-alpine@sha256:<approved-index-digest>' \
  --build-arg DOCKER_CLI_BASE='docker:29-cli@sha256:<approved-index-digest>' \
  --target execution-worker \
  -t greenline-execution-worker .
```

Give this image access only to a dedicated, preferably rootless Docker daemon.
Docker socket or `docker` group access is host-control authority; never share it
with the Control Plane. A network daemon must use authenticated TLS. The worker
and daemon must see the writable Run Bundle root at the same absolute path
(`GREENLINE_RUN_BUNDLE_DIR`, `/run-bundles` by default in the image), because
bind sources are resolved on the daemon host. Mount `/tmp` and that path as
bounded writable filesystems; run the rest read-only with all capabilities
dropped. The worker healthcheck verifies PostgreSQL, the daemon, preloaded
immutable execution images, and this shared-path contract before it is healthy.
Give the worker at least 75 seconds of termination grace so an in-flight
Challenge Run can reach its bounded timeout and remove its container.

### Image release gates

CI builds separate control-plane, worker, Python execution, and Node execution
images from digest-pinned bases. It exports each root filesystem for a Trivy
gate on fixable high/critical vulnerabilities, generates SPDX JSON SBOMs, and
exports OCI archives with embedded SBOM and maximum-provenance attestations.
Successful default-branch builds publish those exact archives to GHCR under
immutable commit tags and add GitHub-signed provenance and SBOM attestations.
Actions, the scanner, PostgreSQL smoke dependency, and BuildKit SBOM generator
are pinned to immutable commits or image digests.

Final Python runtimes do not retain `pip`. The Node execution image contains the
built-in `node:test` runner but removes npm, Corepack, and Yarn. The temporary
Docker CLI exceptions in `.trivyignore.yaml` are scoped to
`usr/local/bin/docker` and expire on 2026-10-01; refresh the Docker CLI base
digest before that date rather than extending the exceptions without review.

`scripts/smoke_images.sh` applies migrations to disposable PostgreSQL, starts
the read-only control-plane and worker images with dropped capabilities, checks
both health contracts and execution toolchains, and verifies graceful shutdown.
`scripts/scan_images.sh` scans unpacked runtime filesystems so third-party base
image SBOM metadata cannot introduce findings for packages absent at runtime.
Protected-environment promotion and digest rollback are documented in
[`RELEASES.md`](RELEASES.md).

Apply PostgreSQL migrations outside the application process before deployment;
see [`backend/migrations/README.md`](backend/migrations/README.md). The runtime
role should have data access but no schema-changing privileges.

Hosted abuse-control defaults and environment overrides are listed in
[`backend/.env.example`](backend/.env.example). Rate budgets use fixed one-minute
windows; audit records retain bounded action/resource metadata, never request
bodies or learner file paths.
Operational security events are emitted as collector-ready JSON with
HMAC-pseudonymized learner subjects and severity levels suitable for alert rules.
Mounted secret files are supported for Clerk, PostgreSQL, and the logging HMAC
key; see [AUTH.md](AUTH.md).

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
   - `variants` — optional additional language implementations. Each key is a
     lowercase variant ID and may override `language`, `runtime`, `readonly`,
     `creatable`, `brief`, `blurb`, and `minutes`.
   Every `conftest.py` and root pytest config stay read-only regardless.
2. Put the broken repo in `repo/`. Python challenges use a pytest suite (and may use a
   root `conftest.py`); other runtimes use the command declared in `runtime`. In every
   case, the failing tests encode the spec.
3. Put fixed files (same relative paths) + `SOLUTION.md` in `solution/`.
4. Verify both states: the repo must fail, `repo/` + `solution/` overlay must pass
   (`python scripts/validate_challenges.py` from `greenline/`).

To add another language to an existing concept, keep the default implementation
in `repo/` and `solution/`, declare it in `variants`, and place its content in
`variants/<variant>/repo/` and `variants/<variant>/solution/`. The catalog keeps
one card and lets the learner choose a language. The default state key remains
the base slug; additional variants use `<slug>@<variant>`.

New content starts in **[QUESTION_BANK.md](QUESTION_BANK.md)**. It tracks researched,
original candidate questions and their implementation status. New specifications must
become broken repositories, tests, and reviewed solutions before entering the catalog.

Use **[PREP_TRACKS.md](PREP_TRACKS.md)** for curated learning paths and the difficulty
ladder. Challenge authors should follow **[CONTENT_CADENCE.md](CONTENT_CADENCE.md)**;
the Node runtime contract and live exercises are documented in
**[SECOND_LANGUAGE_PLAN.md](SECOND_LANGUAGE_PLAN.md)**.

The catalog persists the learner's selected Prep Path in their account-backed Learner
Profile and recommends the next unfinished challenge without hiding the full catalog.
After a successful run, the reference solution offers a short Learning Debrief and a
usefulness rating. Hosted beta operators can inspect the aggregate 30-day funnel and
optional comments with:

```sh
psql "$GREENLINE_DATABASE_URL" --file scripts/product_metrics.sql
```

## Known gaps / backlog

See **[GAPS.md](GAPS.md)** — a detailed, prioritized handoff doc covering every known
gap with file references and suggested implementations. Start there before adding features.

## Notes and limits

- Python and Node challenges are supported through metadata-declared runtime
  commands. Optional Python `requirements.txt` files get content-addressed cached
  environments and are read-only in the workspace; platform dependencies remain
  separate in `backend/requirements.txt`.
- Local Mode's subprocess Adapter is a temp dir + timeout and remains suitable
  only for trusted personal use. The container Adapter provides infrastructure
  isolation, while PostgreSQL provides durable Learner Challenge State, Run
  Jobs, and operation leases. Hosted Mode remains blocked on the remaining
  deployment-readiness work documented in `GAPS.md`.
- Clerk Google sign-in is supported when configured; local development without Clerk
  remains available. Authenticated workspace and progress state is isolated per Clerk user.
