# MakeItGreen — Known Gaps & Improvement Backlog

**Last reconciled with the codebase:** 2026-09-10

**Audience:** an agent (or engineer) picking up work on this codebase with no prior context.
Read `README.md` first for architecture and how to run. This document is the honest,
detailed list of what's missing, why it matters, where the relevant code lives, and
suggested implementation approaches.

## Product context (30 seconds)

MakeItGreen is a local-first clone of [gronex.org](https://gronex.org/) — repository-based
backend interview practice. Core loop: open a challenge (a small broken repo), edit it in
a browser Monaco editor, run the declared test command in an isolated temporary
workspace, make the failing tests green, and compare against a reference solution. The owner uses it to prep for
work-sample style interviews (explore codebase / fix bugs / design features / review
PRs), so features that increase
*interview realism* (timers, structured results, more challenge types) matter more than
generic SaaS features (billing, growth tooling). The AI mock interviewer (gap 4 / #11)
is parked — do not pick it up unless the owner reopens it. Authentication and tenant
isolation are still mandatory gates before production hosting (gap 7), even though they
are not the next interview-prep feature.

**Stack:** FastAPI backend (`backend/`), Vite + React + TS + Monaco frontend
(`frontend/`), file-system challenge content (`challenges/<slug>/{challenge.json,repo/,solution/}`),
SQLite progress. Backend runs on :8000, frontend dev server on :5173 with `/api` proxy.

**Verified:** the full loop works end-to-end (catalog → workspace → red run → edit →
green run → solved state → solution page). A jsdom React integration test now drives
that behavioral practice loop through the real route tree and mocked HTTP boundary. All 49 challenges
validate both ways (broken repo fails, solution overlay passes) via
`scripts/validate_challenges.py`.
The backend currently has 247 passing platform tests covering composition/readiness,
authentication and tenant isolation, file-policy boundaries (including new-file
create/delete), reset safety, mutation concurrency, malformed
content, timeout cleanup, runner outcomes, streaming jobs, challenge environments,
challenge overlays, and API contracts. The current frontend passes `npm test`,
`npm run lint`, and `npm run build`; its 34 tests comprise four dependency-free Node
checks plus 30 Vitest checks covering configured authentication, the design system,
the practice loop, editor failure navigation, and reliable checkpoint restoration. CI is
`.github/workflows/greenline.yml`.

## Open work at a glance

| Priority | Work | Why now |
|---|---|---|
| Now | Deployment operations and capacity evidence | The owner reviewed the architecture; separate app/execution hosts and the G-1 through G-10 evidence remain |
| Next | Operated beta validation | Run the named cohort/burst staging probe, close the launch gates, then observe real queue and learning-loop behavior |
| Beta validation | Observe path → run → solve → debrief → return conversion | Begin once a safely operated beta can collect real usage |
| Later | Retention practice and weekly publishing workflow | Evaluate after the beta learning loop has real usage |
| Parked | AI mock interviewer | Explicitly deferred by the owner |

The local-first feature backlog is complete. The active engineering track is production
readiness, but the service must not receive untrusted public traffic until every remaining
hosting gate is implemented and exercised.

## Current backend safety baseline (do not regress)

These used to be gaps and are now implemented and regression-tested:

- File paths are canonicalized before policy checks. Encoded aliases cannot overwrite
  `tests/`, and paths outside a challenge repo are rejected.
- Every `conftest.py` plus root pytest configuration (`pytest.ini`, `.pytest.ini`,
  `pyproject.toml`, `tox.ini`, `setup.cfg`) is intrinsically read-only. A submission
  cannot make a failing suite green by replacing pytest's hooks or configuration.
- Reset validates the challenge and contains recursive deletion within
  `backend/data/workspaces/`; an unknown challenge returns 404.
- Save, run+progress-recording, and reset+progress-reset are serialized per challenge
  through `backend/challenge_locks.py`. Different challenges remain independent.
- On POSIX, each test command runs in a new process group. A timeout sends TERM to the group, waits
  briefly, then escalates to KILL so spawned descendants do not survive the run.
- Invalid `challenge.json` content and non-UTF-8 challenge files return deterministic
  JSON errors rather than an opaque plain-text 500.
- Hosted Mode requires the signed Clerk `beta_access` claim, returns only summary
  metadata from the catalog, gates solutions on solved/spoiled state, and temporarily
  blocks bulk cross-challenge or solution extraction with PostgreSQL-backed counters.

Relevant regression suites live under `backend/tests/`. These protections make the
local workflow safer; they are not a substitute for production isolation (gap 7).

---

## P0 — directly serves the owner's interview prep

### 1. ~~No timer in the workspace~~ — CLOSED

- **Implemented:** the challenge's `minutes` remains a suggestion; the workspace timer
  is idle until clicked and explicitly started. Its compact picker offers 15 minutes,
  the challenge's suggested duration, and 45 minutes; choosing one starts immediately.
  Once active, clicking the timer pauses or resumes it directly; a small reset action
  appears while paused. State persists per
  slug (`frontend/src/timer.ts`), turns amber at ≤25% remaining and red in overtime,
  freezes at final time on green, and is cleared by workspace Reset.
- **Server-side elapsed:** each run stores `session_elapsed_ms` only after the learner
  starts the timer (see gap 3). Untimed runs store `null`; freeze-on-green still applies.

### 2. ~~Test results are regex-parsed stdout, not structured data~~ — CLOSED

- **Implemented:**
  - Backend: `pytest-json-report` writes a report outside the sandboxed copy;
    `runner.py` returns `tests: [{id, outcome, duration_ms, file, line, message,
    crash_file, crash_line}]` plus summary counts (incl. skipped). Regex parsing
    remains only as a fallback for timeout/collection-crash cases with no report.
  - Frontend: output drawer shows a per-test list (`TestRow`) with failure
    messages; jump buttons open the crash site (preferred) or test definition in
    Monaco via `revealLineInCenter`. Raw pytest log is collapsed under a toggle.
  - Covered by `backend/tests/test_runner.py::test_structured_results_report_per_test_outcomes`.
- **Failure-navigation polish:** `editorDiagnostics.ts` normalizes paths, clamps line
  numbers, adds Monaco error markers/glyphs, and waits for the newly opened model before
  revealing a failure location. React tests cover marker choice and the first-open race.

### 3. ~~No run history / attempt analytics~~ — CLOSED

- **Implemented:**
  - `progress.py` retains the latest ten runs per learner and challenge: wall-clock
    `duration_ms`, optional `session_elapsed_ms` (workspace timer at click), counts,
    exit code, output tail, structured `tests_json`, and the validated workspace overlay
    used by the run.
    Existing SQLite history is pruned per challenge during schema initialization;
    PostgreSQL migration 006 applies the same retention rule.
  - `POST /api/challenges/{slug}/run` accepts `{session_elapsed_ms}` and returns
    `run` + `duration_ms`. `GET /api/challenges/{slug}/runs` lists newest-first.
  - Workspace drawer has RESULTS | HISTORY tabs; selecting a history row reloads
    that run's structured results. A retained snapshot can replace the current workspace
    after confirmation; pending saves settle before restore, and save/run/restore actions
    cannot race. Pre-snapshot history remains visible when retained but cannot be restored.
    Attempts semantics decided: **every run counts** (including post-solve reruns) — see
    gap 17 / backlog #26.
  - Covered by `backend/tests/test_progress.py`, `backend/tests/test_api.py`,
    `backend/tests/test_learner_state.py`, and
    `frontend/tests/workspace-reliability.test.tsx`.

### 3a. ~~No guided, measurable beta learning loop~~ — CLOSED

- **Account-synced guidance:** the catalog stores one of four lightweight Prep Paths
  in the Learner Profile, recommends the next unfinished challenge, and still exposes
  the full catalog. Existing Local Mode browser selections migrate on first load.
- **Post-solve reflection:** solved challenge solutions include one compact Learning
  Debrief for root cause, why the fix works, and the tradeoff. The same form captures
  useful/not-useful and an optional comment; spoiled-but-unsolved solutions cannot
  submit a debrief.
- **First-party measurement:** bounded Product Events cover catalog/return visits,
  path selection, first/successful runs, and debrief/feedback completion. Events do
  not copy source code or free text. `scripts/product_metrics.sql` reports the 30-day
  funnel, per-challenge outcomes, and usefulness feedback directly from PostgreSQL.
- **Durability:** SQLite preserves the Local Mode workflow, while migration 005 adds
  tenant-scoped preferences, debriefs, and events to Hosted Mode PostgreSQL. Hosted
  worker completion records run milestones inside the same fenced transaction.

### 4. No AI mock interviewer (Gronex's differentiator) — PARKED

- **Status:** explicitly deferred. Do not implement unless the owner reopens this.
- **Current:** absent entirely.
- **What Gronex does:** after tests go green, an AI interviewer asks live follow-ups —
  changes a requirement, reviews the updated code, probes trade-offs.
- **Why it matters most here:** the owner is prepping for interviews where the verbal
  follow-up ("why this fix, what breaks at scale, what if we add X") is what's graded.
- **Suggested MVP:** on solved, show an "Interview me" panel. Backend endpoint that
  sends the challenge brief + reference SOLUTION.md + the user's diff (workspace files
  vs repo originals) to an LLM with a rubric-driven system prompt: ask exactly 3
  follow-ups one at a time (a "why" question, a "change this requirement" question, a
  "what breaks at scale" question), then grade each answer against the talking points
  in SOLUTION.md. Needs an API key — make provider/model configurable via env var and
  degrade gracefully (hide the panel) when unset. Each challenge's `challenge.json`
  could optionally carry `followups: [...]` to override generic prompts.

---

## P1 — platform correctness & content pipeline

### 5. ~~New files can't be created — blocks the "Architecture Extension" challenge type~~ — CLOSED

- **Implemented:**
  - `challenge.json` optional `creatable` prefixes (e.g. `["orders/"]`). Create is
    refused outside that whitelist, under `readonly` prefixes, for every
    `conftest.py` / root pytest config, and on path traversal.
  - `POST /api/challenges/{slug}/files/{path}` creates a workspace-only file;
    `DELETE` removes it. Original repo files (and workspace overlays of them)
    cannot be deleted. PUT still updates existing repo or already-created files.
  - `file_tree()` merges workspace-only files and flags them `"new": true`.
  - FILES tab: "+ new file" input when `creatable` is set; delete (×) on NEW
    rows only. `orders-service` has `"creatable": ["orders/"]` for manual checks.
  - Covered by `backend/tests/test_file_access.py` create/delete/file_tree cases.

### 6. ~~Challenge dependencies are coupled to the backend venv~~ — CLOSED

- **Implemented:** optional `runtime.requirements` in `challenge.json` creates a cached,
  content-addressed Python environment under `backend/data/environments/`. The cache key
  includes the Python major/minor version and requirements bytes, so dependency changes
  invalidate it without coupling challenge packages to `backend/requirements.txt`.
- Requirements files are intrinsically read-only through the file API and are rechecked
  before execution. Per-key locks and atomic directory replacement prevent concurrent
  first-run environment corruption. The catalog validator uses the same environment
  contract, and environment behavior has dedicated backend regression tests.

### 7. Production hosting safety modules are implemented; deployment readiness remains

- **Execution seam:** `runner.py` defines the `ChallengeRun`, normalized result,
  streaming callback, and `ExecutionAdapter` contract. Trusted host execution lives
  behind `LocalSubprocessAdapter`; isolated execution lives behind
  `ContainerExecutionAdapter`. Both consume the same validated user-scoped Run Bundle
  and return the same normalized result.
- **Container isolation implemented:** each Run Bundle is mounted read-only into a
  fresh Docker container and copied into a size-bounded tmpfs workspace. The Adapter
  requires digest-pinned, preloaded Python and Node images and disables pulling during
  a run. Its fixed policy disables networking and IPC sharing, makes the root
  filesystem read-only, runs as a numeric non-root user, drops every capability,
  forbids privilege escalation, and enforces CPU, memory/swap, PID, file-descriptor,
  tmpfs, output-tail, and wall-clock limits. Unique names plus a run label support
  force-removal and orphan reconciliation. Container failures never fall back to the
  Local Mode Adapter.
- **Current Local Mode adapter:** it copies a repo into a temporary directory and executes
  it with the backend process's user privileges. The 60-second timeout now terminates
  the full POSIX process group, but there are still no memory/CPU/PID limits, network
  isolation, or filesystem jail. Challenge code can read secrets and mutate anything
  the backend user can access.
- **Durable Learner Challenge State implemented:** `learner_state.py` defines one
  Interface for tenant-scoped workspace overlays, progress, run history, workspace
  snapshots, spoil state, and reset. Local Mode keeps the filesystem/SQLite Adapter.
  The Hosted Mode Adapter stores the aggregate in PostgreSQL with `(user_id, slug)`
  keys, transactional run recording, atomic cascading reset, monotonic workspace
  revisions, the latest ten restorable run checkpoints, bounded output history, and an
  exact schema-version readiness check.
  Migrations are explicit deployment artifacts and never run under the application
  role. Container execution now requires an injected durable workspace snapshot, so
  it cannot discover or fall back to filesystem learner state.
- **Durable Run Jobs and leases implemented:** `run_coordination.py` stores queued,
  running, and terminal jobs in PostgreSQL. Enqueue acquires a monotonically fenced
  operation lease for one `(user_id, slug)` aggregate. Disposable workers use
  expiring claim tokens, heartbeat both claim and lease, stream bounded output, and
  atomically persist progress, Challenge Run history, the terminal result, and lease
  release. `FOR UPDATE SKIP LOCKED` supports competing workers; stale claims cannot
  publish output or results. Workspace mutations refuse a live lease and safely retire
  an expired one. Local Mode retains its in-process implementation.
- **Abuse controls implemented:** `abuse_controls.py` rejects declared or streamed
  request bodies over the configured byte limit before parsing. Authenticated Hosted
  Mode requests use PostgreSQL-backed fixed-window per-learner budgets, with stricter
  mutation, Challenge Run, and Challenge Content budgets. Hourly counters detect access
  across unusually many distinct challenges or solutions and temporarily block it;
  blocked bulk extraction emits a bounded security event without recording file paths.
  Request admission durably creates a bounded,
  tenant-scoped audit event before route mutation; repeated rate-limit rejections are
  aggregated per learner/scope/window to prevent audit amplification, and unavailable admission fails closed.
  Run Job enqueue uses a PostgreSQL transaction advisory lock to enforce global and
  per-learner active capacity without a cross-replica check-then-insert race. Limits
  and audit retention are validated immutable startup policy; Local Mode remains
  unrestricted.
- **Persisted-overlay trust (local hole closed):** every persisted overlay is now
  canonicalized and rechecked against ignored, read-only, requirements, and creatable
  policies immediately before copying. Invalid or symlinked workspace entries refuse
  the run. In production, trusted tests/config should still be mounted separately and
  read-only rather than relying only on application policy.
- **Grading integrity:** candidate code and its test process share an execution boundary. A
  deliberately adversarial submission can interfere with the test process even when
  tests/config are read-only. Host isolation protects infrastructure; trustworthy
  scoring may additionally require a trusted supervisor and a protocol that does not
  accept the candidate process's exit status as the sole source of truth.
- **Current API/state:** Clerk bearer-token verification is enforced whenever
  `CLERK_SECRET_KEY` is configured; Hosted Mode additionally requires the verified
  `beta_access: true` session claim, and deployment guidance requires Clerk Invite-only
  mode. The frontend exposes Google-only sign-in when `VITE_CLERK_PUBLISHABLE_KEY` is
  configured. Authenticated workspaces, progress, and run history are isolated by
  Clerk's verified `sub`. The catalog exposes only browsing summaries; full briefs and
  repository content remain per-challenge reads, and reference solutions require that
  learner's solved or spoiled state. CORS is a
  browser policy, not an access-control boundary;
  non-browser clients can call the code-execution endpoint directly when auth is not
  configured in Local Mode. `challenge_locks.py` remains the Local Mode mechanism;
  Hosted Mode coordinates and admits requests through PostgreSQL instead.
- **Fail-closed composition gate:** `GREENLINE_MODE` is mandatory. Local Mode preserves
  the trusted personal workflow. Hosted Mode requires complete Clerk configuration and
  PostgreSQL control-plane Adapters. It has a disabled execution Adapter and cannot start
  its own workers. The separate worker process requires a concrete container Adapter
  configured with both immutable image digests; arbitrary placeholder objects cannot
  bypass either process's composition gate. Mismatched capacity policies are rejected.
- **Role-specific readiness implemented:** API `/health/ready` dynamically checks only
  the PostgreSQL dependencies needed to admit, enqueue, and observe work. The worker
  verifies the Docker daemon and both exact digest-pinned execution images before it
  starts claiming jobs, proves the daemon can bind its shared Run Bundle storage, and
  never pulls an image. Its container healthcheck repeats the full worker composition.
  Worker loss no longer makes the public control plane unavailable.
  `/health/release` adds the immutable build commit to the same readiness contract
  so rollout automation cannot mistake an old healthy revision for the promoted one.
- **Operational configuration implemented:** secrets support mutually exclusive direct
  or absolute mounted-file sources and invalid sources fail without value disclosure.
  The supported `serve.py` launcher configures Uvicorn with explicit trusted proxy
  networks; wildcard trust and direct Hosted startup are refused. Security events use
  server request IDs, bounded fields, severity, and stable HMAC-pseudonymized learner
  subjects. They are emitted as one-line JSON for collection and alert rules without
  tokens, raw subjects, request bodies, file paths, or database URLs.
- **Deployment bundle implemented:** separate application and execution-worker
  Compose manifests, a Caddy edge, PostgreSQL TLS enforcement, digest-only release
  settings, least-secret mounts, and a fail-closed preflight validator are checked in
  under `deploy/`. The validator rejects a public database bind, mutable images,
  mismatched shared policy, a Docker socket in the application trust zone, and Clerk
  credentials in the worker trust zone.
- **Remaining deployment gate:** do not expose the service to untrusted users yet.
  The live deployment must still provide secret delivery/rotation, direct-port
  network isolation, edge DDoS limits, a JSON-log collector with concrete alert rules,
  durable audit export, backup/restore drills, separate application/database and
  execution hosts, and measured capacity evidence.
- **Capacity baseline implemented:** one active run per learner is the fail-closed
  default, global queued/running capacity remains independently bounded, per-host worker
  concurrency stays configurable, and container memory is configurable with a validated
  128–4096 MiB range. `scripts/execution_capacity_probe.py` defines a 15-learner burst,
  50/100-learner five-minute cohorts, a 100-submission/10-second peak burst, and a
  25-learner retry burst against a mixed Python/Node workload on the real PostgreSQL
  queue and worker pool.
- **Suggested sequence:** install and validate the two Compose deployments, close the
  live network and secret gates, then capture backup/restore, adversarial execution,
  and capacity evidence in gap 15.

### 8. ~~Runs are synchronous and non-streaming~~ — CLOSED

- **Implemented:** `POST /api/challenges/{slug}/runs` returns a background `run_id`
  with HTTP 202; `GET /api/run-jobs/{run_id}?after=<offset>` returns incremental output,
  state, truncation metadata, and the final structured result. The workspace polls and
  appends output while the suite is still running, then refreshes progress and history.
- The legacy synchronous endpoint remains for compatibility. Background jobs retain the
  per-challenge operation lease for the whole run, and rolling absolute offsets keep
  polling correct after the 20k output cap. API, runner-callback, and job-store tests
  cover start/poll/completion, streaming, truncation, and unknown jobs.

### 9. ~~Content parity foundation~~ — CLOSED

- **Current types covered:** Concurrency (`orders-service`), Repository Implementation
  (`wallet-service`), API Contract Debugging (`ledger-api`), Incident Debugging
  (`incident-alerts`), Database Engineering (`booking-db`), Architecture Extension
  (`webhook-ext`), Runtime Diagnostics (`report-latency` — readonly profiler dump,
  Θ(customers·orders) nested scans; correctness green, pass-count invariant red).
- **Depth challenges:** `transfer-deadlock`, `rate-limiter`, `log-aggregator`,
  `metrics-rollups`, `pagination-api`, `deploy-crash`, `outbox-publish`, `cache-ext`,
  `thread-stall`, `topk-errors`, `return-workflow`, `project-vault-api`,
  `audit-export-pool`, `device-ingest-incident`, `invoice-delivery-worker`,
  `release-gates`, `invoice-cents-migration`, `workspace-replica-router`,
  `build-stream-leak`, and `artifact-upload-ext` add multiple scenarios and difficulty
  levels across every type. `subscription-renew` adds a Tier 3 multi-invariant Python
  scenario, while `webhook-batch-node` establishes the JavaScript/Node runtime. Orders
  30–39 add optimistic revisioning, lease fencing, CDC projection, a second Node
  extension, ordered webhooks, timeout incidents, bounded export, condition-variable
  shutdown, catalog reconciliation, and SQL window isolation. Orders 40–45 add resilient
  CSV ingestion, tenant-safe cached authorization, retry-storm control, last-known-good
  feature flags, allocation-pressure diagnosis, and multi-slot CDC retention. See
  `CHALLENGE_BACKLOG.md` for the full content roadmap.
- **Guidance and cadence:** `PREP_TRACKS.md` provides curated paths and a difficulty
  ladder; `CONTENT_CADENCE.md` defines the weekly release rhythm and validation gates;
  `SECOND_LANGUAGE_PLAN.md` documents the Node and language-variant contracts.
  Six concepts now have paired Python/JavaScript implementations, alongside two
  Node-native challenges. Further language coverage is ongoing reviewed content
  work, not an unimplemented platform capability.
- **Authoring recipe** is in `README.md` ("Adding a challenge"); the validation
  discipline that MUST be kept: broken `repo/` fails its declared suite; `repo/` + `solution/`
  overlay passes. `scripts/validate_challenges.py` asserts both states for every
  challenge; CI runs it (gap 14).

---

## P2 — UX quality

### 10. ~~Solutions are ungated spoilers~~ — CLOSED

- **Implemented:** `progress.spoiled` column (migrated on existing DBs) plus
  `POST /api/challenges/{slug}/spoil`. The client records spoiled after confirm,
  and the backend refuses `GET /solution` unless that learner is solved or spoiled.
  - Workspace Solution links: unsaved confirm, then spoil confirm unless already
    solved or spoiled. Fail to record → stay put.
  - Direct `/c/:slug/solution` shows a Confirm / Back panel when not solved/spoiled.
  - Catalog shows an amber `SPOILED` pill next to the status pill.
  - Reset deletes the row (spoiled clears with it).
- Covered by `backend/tests/test_progress.py` (store + migration) and
  `test_api.py` spoil contract.

### 11. ~~Solution page has no real diff view~~ — CLOSED

- **Implemented:** Monaco `DiffEditor` is the default view per solution file
  (side-by-side, unchanged regions collapsed), with `broken`/`fixed` full-file toggles.
  Shared editor theme extracted to `frontend/src/monacoTheme.ts`.
- Page-level compare: `broken → fixed` (default) and `yours → fixed` (workspace
  file via `GET /files/{path}`; missing files show empty / "not in your workspace").

### 12. ~~Editor ergonomics~~ — CLOSED

- **Implemented** in `Workspace.tsx` + `GET /api/challenges/{slug}/search`:
  - Multiple editor tabs (`openTabs`), × / middle-click to close
  - Cmd/Ctrl+S saves the current file with a "saved" flash
  - `beforeunload` + `useBlocker` (data router) + confirm on back/Solution links
  - SEARCH side tab + Cmd/Ctrl+Shift+F; click a hit to jump to file:line
- Covered by `test_search_*` in `backend/tests/test_file_access.py`.

### 13. ~~Missing UI states~~ — CLOSED

- **Errors:** Catalog / Workspace initial load / Solution use `LoadError` with retry.
- **StrictMode double-fetch:** CLOSED. Mount effects use `AbortController`;
  `api.*` accept `{ signal }`; aborted fetches are ignored via `isAbortError`.
- **Narrow-viewport workspace:** CLOSED. Below Tailwind's `lg` breakpoint (1024px),
  the editor fills the workspace and the header **Panel** control toggles the
  brief/files/search panel as an absolute overlay. Tailwind's `hidden` / `flex`
  utilities control its collapsed and open states. Opening a file auto-hides it.

---

## P3 — engineering hygiene

### 14. ~~Platform test coverage~~ — CLOSED

- **Implemented:** 247 backend tests now also cover composition/readiness,
  authentication, tenant isolation, `progress.py` (attempts, sticky
  `solved_at`, non-downgrade, reset, concurrent SQLite, spoiled), `runner.py`
  (green/red/no-tests, stdout+stderr, truncation, container isolation policy), `challenges.py`
  (overlay `read_file`, `edited`/`new` flags, `solution_files`, metadata shapes),
  and API contracts for catalog/detail/run/solution/spoil.
- **Content CI:** `scripts/validate_challenges.py` asserts every challenge's
  pristine `repo/` fails and `repo/` + `solution/` overlay passes. Wired in
  `.github/workflows/greenline.yml` (backend pytest + validator + frontend tests,
  lint, and build).
- **Frontend practice loop:** `frontend/tests/practice-loop.test.tsx` renders the real
  React Router tree and drives catalog → workspace → failing run → edit/save → green
  run → solved state → solution. The HTTP boundary and Monaco widget are replaced with
  deterministic test adapters; page orchestration, navigation, checkpoint restoration,
  and state transitions remain production code. `npm test` runs this Vitest/jsdom suite
  after four dependency-free Node checks, so CI executes both layers.
- **PostgreSQL contracts:** Learner State, Run Jobs/capacity, and request
  admission/audit behavior run against migrated PostgreSQL when
  `GREENLINE_TEST_DATABASE_URL` is configured. These are skipped on machines without
  the disposable integration database.

### 15. Deployment foundation — IN PROGRESS

- **Implemented foundation:** application construction now goes through one
  `create_application` composition interface. Runtime mode and identity configuration
  are snapshotted and validated before the application is returned. `/health/live`
  reports process liveness, while `/health/ready` remains closed until FastAPI lifespan
  startup validates all control-plane PostgreSQL Adapters. A separate fail-closed worker
  owns container execution. Hosted Mode uses explicit SQL migrations, durable Learner
  Challenge State, fenced Run Jobs, and PostgreSQL request admission/audit controls.
- **Implemented packaging:** the multi-stage root `Dockerfile` builds Vite assets and
  serves them from the FastAPI control plane with API-first route precedence and SPA
  fallback. Its runtime is numeric non-root, excludes test/development dependencies, and
  intentionally contains no Docker CLI. Immutable base-image references are mandatory.
- **Implemented worker artifact:** `Dockerfile.worker` produces a separate numeric
  non-root worker with only PostgreSQL and Docker-CLI runtime dependencies. It requires
  digest-pinned compatible bases, a dedicated daemon, preloaded immutable execution
  images, and a shared absolute Run Bundle path visible to both worker and daemon.
- **Implemented release gates:** CI builds four runtime images from immutable bases,
  scans their unpacked filesystems for fixable high/critical vulnerabilities, runs a
  disposable PostgreSQL/control-plane/worker deployment smoke, emits SPDX SBOMs and
  maximum-provenance OCI archives, and signs provenance plus SBOM attestations on
  trusted push builds. Python package installers and Node package managers are absent
  from final execution images. The only scanner exceptions are path-scoped Docker CLI
  findings with an automatic 2026-10-01 expiry.
- **Implemented release control:** successful default-branch builds publish the exact
  scanned OCI archives to GHCR under collision-protected immutable commit tags. A
  separate serialized workflow moves existing digests to `staging` or `production`
  only through deliberately configured GitHub Environments and emits promotion or
  rollback records. Promotions poll an environment-specific HTTPS release endpoint for
  the exact commit and automatically restore the complete previous digest set on
  timeout or unhealthy rollout. Runnable-manifest identity is checked between scanned
  images and attested archives, and the release records are attested. No promotion or
  rollback rebuilds an image.
- **Still current:** Local Mode uses SQLite + filesystem state under `backend/data/`.
  Production deployment-platform secret rotation, direct-port network isolation, an external log
  collector/alerts, durable audit export, backup/restore policy and drills, registry
  retention policy, the hosting platform's tag-watcher/deployment-controller
  configuration, permanent external release-record export, live deployment evidence,
  and real-host capacity evidence remain missing.
- **Required deployment shape:** the web/API Control Plane may serve `frontend/dist`
  from one image on the stateful application/database host. Untrusted test execution
  must run on a separate execution host pool with no Clerk secret or public listener.
  Start each 1 GiB staging worker at 384 MiB per run and concurrency one, then resize or
  add workers based on named cohort/burst probe evidence rather than treating one as a
  global production concurrency limit. The invited beta keeps PostgreSQL on the
  application Droplet; before the public launch, rehearse and complete the provider-neutral
  Neon cutover in [`MIGRATE_NEON.md`](MIGRATE_NEON.md). Add backup/restore drills, deployment rollout
  integration, structured log collection, and operational alerting before public traffic.

### 16. ~~Runtime state and generated files are not ignored~~ — CLOSED

- **Implemented:** `greenline/.gitignore` covers Python/test caches, venvs,
  `backend/data/` (progress DB, workspaces, future run logs), frontend
  `node_modules`/`dist`, and OS artifacts. Verified: `git status --untracked-files=all`
  shows no runtime state.

### 17. ~~Misc smaller items~~ — CLOSED

- ~~`runner.py` `SUMMARY_RE`~~ — already removed; `_parse_counts` is the only parser.
- ~~Output truncated with no UI notice~~ — runner returns `output_truncated`; Workspace
  shows an amber notice when set.
- ~~`order` undocumented~~ — listed in the README authoring recipe.
- ~~Landing LIVE badges hardcoded~~ — derived from catalog challenge types.
- ~~Progress `attempts` increments on every run including post-solve reruns~~ —
  **decided:** every run counts (backlog #26). Documented in `progress.py`.
- ~~Meta / OG tags~~ — description plus Open Graph and large-card Twitter metadata in
  `frontend/index.html`, backed by the project-owned 1200×630
  `frontend/public/og-makeitgreen.png` asset. Production may replace the root-relative
  URL with the final canonical absolute URL at deploy time.

---

## Suggested execution order

The local-first backlog through this pass is complete: runtime overlay validation,
streaming jobs, isolated challenge dependencies, Monaco failure navigation, restorable
run checkpoints, the first three content batches and Node challenges, learning
tracks/cadence, and the social-preview asset are implemented and tested.

The owner-reviewed production architecture is documented in
[`THREAT_MODEL.md`](THREAT_MODEL.md): manual copying remains an accepted invite-only beta
limitation, while untrusted execution must use hosts separate from the application and
database. Close launch gates G-1 through G-10 with durable evidence, including the
named 15/50/100-learner cohort/burst capacity probe and its explicit queue-start SLOs.
Finalize direct-port
isolation, secret rotation, collector-backed security alerts, durable audit export,
backup/restore drills, registry retention, deployment-controller configuration, and
permanent release-record export. Only after those controls are implemented and exercised
should the hosted beta accept untrusted traffic and begin measuring the learning funnel.

This table tracks the currently identified backlog, including minor items; it is a
living inventory rather than a guarantee that no further work will be discovered.
Numbers are stable IDs, not a mandated order. Row 8 is a tracking umbrella for rows
13–16, not additional implementation work. Rows 9 and 31 together record the completed
gap 14 foundation and frontend behavioral coverage.

| # | Item | Effort | Payoff | Status |
|---|---|---|---|---|
| 1 | Workspace timer (gap 1) | S | High (interview realism) | ✅ done |
| 2 | `.gitignore` for runtime state (gap 16) | S | Hygiene | ✅ done |
| 3 | Monaco DiffEditor on solution page (gap 11) | S | Medium | ✅ done |
| 4 | Structured test results + per-test UI (gap 2) | M | High | ✅ done |
| 5 | Run history, elapsed time, and checkpoints (gaps 3, 1 leftover) | S–M | Medium | ✅ done |
| 6 | New-file support (gap 5) | M | Unblocks new content type | ✅ done |
| 7 | Incident Debugging challenge (gap 9) | M | High for the owner | ✅ done (`incident-alerts`) |
| 7b | Database Engineering challenge (gap 9) | M | High for the owner | ✅ done (`booking-db`) |
| 7c | Architecture Extension challenge (gap 9) | M | High for the owner | ✅ done (`webhook-ext`) |
| 7d | Runtime Diagnostics challenge (gap 9) | M | High for the owner | ✅ done (`report-latency`) |
| 8 | Editor ergonomics bundle (gap 12; split as 13–16 below) | M | Medium | ✅ done |
| 9 | Platform tests + content validation CI foundation (gap 14) | S–M | Compounding | ✅ done |
| 10 | Streaming runs + per-challenge venvs (gaps 8, 6) | L | Medium | ✅ done |
| 11 | AI interviewer (gap 4) | L | Parked — owner said skip for now | ⏸ deferred |
| 12 | Threat model + deployment operations (gaps 7, 15) | L | Blocks hosting | ◐ architecture reviewed; deployment and capacity evidence next |
| 13 | Multiple editor tabs (gap 12) | S–M | Medium | ✅ done |
| 14 | Cmd+S save + "saved" indicator (gap 12) | S | Medium | ✅ done |
| 15 | Unsaved-changes guard on navigation (gap 12) | S | Medium | ✅ done |
| 16 | Cross-file search within a challenge (gap 12) | M | Medium (explore phase) | ✅ done |
| 17 | Solution spoiler-gating + `spoiled` progress flag (gap 10) | S | Medium (incentives) | ✅ done |
| 18 | Diff user's workspace vs reference solution (gap 11 bonus) | S | Medium | ✅ done |
| 19 | Error/retry UI states when backend is down (gap 13) | S | Medium | ✅ done |
| 20 | Guard StrictMode double-fetch with abort controller (gap 13) | S | Low | ✅ done |
| 21 | Narrow-viewport workspace layout that stacks (gap 13) | M | Low–Medium | ✅ done |
| 22 | Remove dead `SUMMARY_RE` constant in `runner.py` (gap 17) | XS | Hygiene | ✅ done (already gone) |
| 23 | UI notice when output is truncated at 20k chars (gap 17) | XS | Low | ✅ done |
| 24 | Document `order` field in README authoring recipe (gap 17) | XS | Hygiene | ✅ done |
| 25 | Derive landing "LIVE" type badges from catalog (gap 17) | XS | Low | ✅ done |
| 26 | Decide attempts semantics for post-solve reruns (gap 17) | XS | Blocks 5's design | ✅ done (every run counts) |
| 27 | Meta description + Open Graph tags (gap 17) | XS | Low | ✅ done; project image tracked in row 30 |
| 28 | Structured-result jump marker + first-open reveal polish (gap 2 follow-up) | S | Medium (failure navigation) | ✅ done |
| 29 | Content parity expansion: Tier 3, second language, release cadence, and track guide (gap 9) | L | High (catalog depth) | ✅ done (`subscription-renew`, `webhook-batch-node`, guides) |
| 30 | Add and host an `og:image` social-preview asset (gap 17 follow-up) | XS | Low | ✅ project asset done; canonical absolute URL waits for production domain |
| 31 | Frontend behavioral practice-loop component/browser coverage (gap 14) | M | High (regression confidence) | ✅ done (React/jsdom integration) |
| 32 | Revalidate persisted workspace overlays before copying them into a run (gap 7 local safety) | S | High (execution policy) | ✅ done |

**Conventions to preserve:** challenge validation discipline (both states verified);
tests and pytest control files are enforced read-only by the backend (the UI flag is
informational, not the security boundary); save/run/reset ordering remains atomic per
challenge; `DESIGN.md` is the canonical visual specification. New product and
marketing UI uses Tailwind CSS v4 with semantic tokens from
`frontend/src/styles/globals.css` and locally owned shadcn-style primitives in
`frontend/src/components/ui/`. Keep custom CSS narrowly scoped to the Monaco theme
bridge, prose, and effects that utilities cannot express cleanly; do not
introduce colors outside the documented structural, semantic, and decorative palettes;
keep the backend
dependency-light and the whole thing runnable with two commands.
