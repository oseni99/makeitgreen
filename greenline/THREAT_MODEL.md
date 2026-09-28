# MakeItGreen production threat model

**Status:** owner-reviewed architecture baseline; launch approval pending

**Last reconciled with the codebase:** 2026-09-28

**Target deployment:** authenticated self-service access with the public
application/database and untrusted-code Execution Worker pool on separate
DigitalOcean Droplets, following
[`DEPLOY_DIGITALOCEAN.md`](DEPLOY_DIGITALOCEAN.md)

This document defines what MakeItGreen must protect before Hosted Mode receives
untrusted traffic. It separates controls already enforced by the application from
controls that only the deployment can provide. A green application test suite is
not evidence that the deployment gates below are satisfied.

## Executive decision

MakeItGreen treats every signed-in learner and every submitted repository as
untrusted. Self-service registration does not weaken the execution boundary, but
it increases capacity, abuse, scraping, recovery, and monitoring pressure. Every
`G-*` launch gate still requires passing evidence, and the owner must explicitly
accept the unavoidable content-copying limitation:

1. An authorized learner can still copy content manually or coordinate across
   accounts. The product can make bulk extraction expensive and detectable, but
   cannot make content shown in a browser impossible to copy.

Clerk authentication is an identity boundary, not a sandbox or an enrollment
allowlist. Any authenticated account must be treated as hostile when it submits
source code. The owner requires a separate execution host rather than accepting
the previous single-host Docker/kernel risk.

## Scope and assumptions

### In scope

- The React/Monaco browser client and Clerk session handling.
- The public FastAPI Control Plane in Hosted Mode.
- Immutable challenge metadata, starter repositories, tests, and solutions.
- PostgreSQL Learner Challenge State, Run Jobs, rate limits, audits, product events,
  and worker release heartbeats.
- The non-HTTP Execution Worker pool, per-host Run Bundle directories, Docker
  daemons, and disposable Python and Node Challenge Run containers.
- Caddy, Cloudflare DNS, the DigitalOcean hosts/firewalls/VPC, backups, and log
  export.
- GitHub Actions, GHCR images, attestations, promotion, and rollback.
- Clerk, Google OAuth, operator accounts, secrets, and administrative actions.

### Out of scope

- Local Mode. It is a trusted personal workflow and must never receive untrusted
  traffic.
- Denial or compromise of Clerk, Google, GitHub, Cloudflare, DigitalOcean, or the
  operator's endpoint beyond the controls those providers expose. Their compromise
  remains a dependency risk.
- Preventing a legitimate learner from remembering, photographing, transcribing, or
  rewriting content that the product intentionally displays.
- Perfect grading against an adversarial candidate process. Infrastructure isolation
  is required for beta; stronger trusted-supervisor grading is a later integrity
  improvement.

### Deployment assumptions

- `makeitgreen.dev` is the only public application origin.
- `accounts.makeitgreen.dev` and `clerk.makeitgreen.dev` remain Clerk-managed.
- Only Caddy exposes ports 80 and 443. SSH is restricted to the administrator's
  current IP. FastAPI, PostgreSQL, the worker, and the Docker API have no public port.
- The application/database host and every execution host are dedicated to
  MakeItGreen and do not host unrelated workloads.
- PostgreSQL listens only on the application host's private VPC interface, requires
  TLS across hosts, and admits remote connections only from the execution-worker
  pool; the local Control Plane connects through its private application network.
- Per-user active runs are limited to one. Global queue capacity and per-host worker
  concurrency are independently configured from named capacity evidence. Normal
  50/100-learner cohorts must begin 95% of runs within ten seconds; the 15-learner
  and retry bursts plus the 100-learner peak burst must begin 95% within thirty
  seconds. No normal-cohort run may wait over thirty seconds and no burst run over
  sixty seconds.
- Challenge content and execution images are trusted release inputs. Learner
  workspace overlays and their runtime behavior are untrusted.

## System and trust boundaries

```mermaid
flowchart LR
    U[Authenticated learner browser] -->|HTTPS| E[Cloudflare DNS / Internet edge]
    E -->|HTTPS| C[Caddy]
    C -->|private network| A[Control Plane]
    U <-->|session and OAuth| K[Clerk / Google]
    A -->|token verification| K
    A -->|parameterized SQL| P[(PostgreSQL)]
    W[Separate Execution Worker pool] -->|private VPC: claim and complete| P
    W -->|local Docker API| D[Worker-host Docker daemon]
    D -->|fresh container| R[Challenge Run]
    W -->|stage| B[Run Bundle directory]
    R -->|read-only bind| B
    G[GitHub Actions / GHCR] -->|digest-pinned release| A
    G -->|digest-pinned release| W
    G -->|preloaded digest| D
```

| Boundary | Less-trusted side | More-sensitive side | Required enforcement |
|---|---|---|---|
| TB-1 Internet edge | Anonymous network client | Caddy and application origin | TLS, edge request limits, DDoS controls, no direct backend port |
| TB-2 Browser/API | Browser and bearer token | Control Plane and learner data | Clerk signature/session validation, authorized-party allowlist, request-size and rate limits |
| TB-3 Identity provider | OAuth/session response | Application authorization | Production Clerk keys, Google OAuth credentials, Open access mode, session revocation procedure |
| TB-4 Control Plane/database | Public request-derived values | All durable tenant state | Parameterized queries, `user_id` from verified `sub`, least-privilege application role, backups and audit export |
| TB-5 Application host/worker pool | Enqueued job and restricted worker DB role | Execution authority and durable tenant state | Private VPC with TLS/firewall, PostgreSQL queue, fenced claims and leases, no Docker socket or CLI on the application host |
| TB-6 Worker/Docker | Worker process | Host-level container authority | Dedicated execution hosts, restricted host access, exact images, runtime readiness, host patching; worker compromise is execution-host compromise |
| TB-7 Run Bundle/container | Learner-controlled overlay | Host and trusted challenge inputs | Revalidation, read-only bind, private propagation, tmpfs copy, no network, non-root UID, read-only root, dropped capabilities, resource limits |
| TB-8 CI/runtime | Repository and build workflow | Deployable artifacts | Pinned actions/bases, scans, SBOMs, provenance, immutable digests, protected promotion and rollback |
| TB-9 Operator/control planes | Human administrator | DNS, identity, cloud, registry, secrets | MFA/passkeys, least privilege, recovery codes, credential rotation, auditable changes |

## Assets and security objectives

| ID | Asset | Confidentiality | Integrity | Availability |
|---|---|---:|---:|---:|
| A-1 | Challenge briefs, repositories, tests, and reference solutions | High — core product content | High | Medium |
| A-2 | Learner workspace files, run output/history, debriefs, and progress | High | High | Medium |
| A-3 | Clerk sessions, Google OAuth configuration, beta authorization | High | High | High |
| A-4 | Clerk, database, registry, SSH, backup, and log-pseudonym secrets | Critical | Critical | High |
| A-5 | PostgreSQL state, audit records, and release heartbeats | High | Critical | High |
| A-6 | Execution host, Docker daemon, and Run Bundle storage | Critical | Critical | High |
| A-7 | Release images, challenge content, SBOMs, and promotion records | Medium | Critical | High |
| A-8 | Service capacity and the operator's cloud spend | Low | Medium | High |

## Actors

- **Anonymous client:** has network access but no valid Clerk session.
- **Authenticated learner:** may read authorized content and submit arbitrary source code.
- **Malicious authenticated learner:** deliberately scrapes, exhausts capacity, tampers with
  grading, probes tenant boundaries, or attempts container escape.
- **Compromised learner account:** possesses a valid session without the owner's
  consent.
- **Distributed extractor:** coordinates multiple self-created or compromised accounts to
  stay below per-user limits.
- **Supply-chain attacker:** attempts to alter source, dependencies, Actions, images,
  tags, or release records.
- **Compromised application component:** gains the privileges of the Control Plane,
  worker, database role, or log collector.
- **Operator error or compromise:** misconfigures Hosted Mode, exposes a port, leaks a
  secret, configures identity incorrectly, or deploys the wrong release.

## Invariants enforced by the application

These claims are present in code and tests. The deployment must not bypass them.

1. `GREENLINE_MODE` is mandatory. Hosted Mode fails composition unless Clerk,
   PostgreSQL state, durable Run Jobs, abuse controls, trusted proxies, security
   logging, process role, and immutable release identity are configured.
2. Every Hosted `/api/*` request requires a verified Clerk session whose `azp` is in
   `CLERK_AUTHORIZED_PARTIES`. Self-service registration does not permit anonymous API
   access.
3. Learner identity comes only from the verified Clerk `sub`; request bodies and URLs
   cannot choose a tenant ID.
4. The Hosted Control Plane uses a disabled execution adapter and contains neither the
   Docker CLI nor the Docker socket.
5. The Execution Worker has no HTTP listener or Clerk secret. It receives work through
   PostgreSQL and requires a current claim token plus a monotonically fenced Operation
   Lease to publish output or results.
6. Hosted learner state, coordination, request admission, content-access counters, and
   audit records use PostgreSQL and require the exact migration version.
7. Persisted workspace overlays are canonicalized and revalidated before a Run Bundle
   is created. Traversal, symlinks, protected tests/configuration, and unauthorized new
   paths are rejected.
8. Challenge Run images are preloaded and addressed by digest. The worker never pulls
   an execution image while serving a learner.
9. Each Challenge Run uses a fresh container with networking and IPC disabled, a
   read-only root, a numeric non-root user, all capabilities dropped, no privilege
   escalation, and bounded CPU, memory/swap, PIDs, file descriptors, tmpfs, output, and
   wall time.
10. Hosted catalog responses expose browsing summaries only. Detailed challenge
    content is metered, and solutions require that learner's solved or spoiled state.
11. Security logs pseudonymize Clerk subjects and exclude tokens, raw subjects,
    request bodies, learner paths, and database URLs.
12. Release readiness includes the exact source commit, at least one fresh matching
    worker, and the exact Python and Node execution-image references.

## Threat register

Risk is the expected production risk **after current application controls but before missing
deployment gates**: Critical, High, Medium, or Low.

### Identity and authorization

| ID | Threat and impact | Existing control | Residual risk / required treatment | Risk |
|---|---|---|---|---:|
| T-ID-1 | Anonymous access to the API | Clerk verification and exact authorized-party configuration | Prove Production keys and authorized parties are used; test no-token, invalid-token, and wrong-`azp` requests against the deployed edge | Medium |
| T-ID-2 | Automated account creation is used to spam runs or evade per-user limits | Clerk-managed sign-up, durable per-user limits, global run capacity, and request auditing | Exercise sign-up abuse protections, monitor account/run creation, retain the global capacity ceiling, and add edge or identity-provider controls if abuse appears | Medium |
| T-ID-3 | Stolen session or OAuth account permits authorized access | Clerk/Google session controls and revocation | Require MFA/passkeys for all operator accounts; define learner-session revocation and incident response; avoid long-lived credentials in browsers | Medium |
| T-ID-4 | Forged or stale sessions are trusted | Tokens are signature-, issuer-, time-, and authorized-party-verified | End a user's Clerk sessions when revoking access and verify the revocation drill | Low |
| T-ID-5 | OAuth or DNS misconfiguration redirects users to an attacker | Clerk-managed subdomains and configured Google callback | Lock down Cloudflare, Clerk, and Google accounts with MFA; inventory exact origins/callbacks; alert on DNS changes | Medium |

### Tenant data and application input

| ID | Threat and impact | Existing control | Residual risk / required treatment | Risk |
|---|---|---|---|---:|
| T-DATA-1 | IDOR exposes or changes another learner's workspace, jobs, history, or debrief | Verified `sub` supplies `user_id`; state and job queries are tenant-scoped; behavioral tests cover isolation | API and worker roles can still access multiple tenants and PostgreSQL RLS is not implemented. Keep the DB on the private VPC, give each process only its required grants, retain cross-tenant tests for every new endpoint, and evaluate RLS before multi-tenant scale | Medium |
| T-DATA-2 | Path traversal, symlink, or protected-file overwrite changes trusted tests or host files | Canonical path policy, intrinsic read-only files, creatable allowlist, overlay revalidation, read-only Run Bundle | Keep validation tests in CI; treat any new file API or archive import as a new threat-model review trigger | Low |
| T-DATA-3 | SQL injection corrupts or discloses PostgreSQL | Current adapters use parameterized queries and bounded enums/actions | Maintain parameterization; prohibit request-derived SQL identifiers; DB role must have no DDL or role-management privileges | Low |
| T-DATA-4 | Oversized bodies, outputs, free text, or histories exhaust memory/storage | 256 KiB request default, bounded fields, 20k output, ten run checkpoints, retention/pruning | Add disk/DB growth alerts and quotas; load-test chunked bodies and repeated allowed-size writes | Medium |
| T-DATA-5 | Learners put secrets or personal data in workspaces/debriefs; backups or support access expose it | No source or free text in Product Events/security logs | Publish a privacy notice, restrict backup/log access, define deletion/retention, and never use learner content for support without consent | Medium |
| T-DATA-6 | Browser-rendered learner or challenge text executes script and steals a token | React escapes text; Markdown is rendered without an intentional raw-HTML path | Add deployment CSP and regression tests for hostile Markdown/file names; review any future HTML/preview plugin as a security-sensitive change | Medium |

### Untrusted code execution

| ID | Threat and impact | Existing control | Residual risk / required treatment | Risk |
|---|---|---|---|---:|
| T-EXEC-1 | Learner code reads service secrets or mutates the Control Plane | Separate non-HTTP worker; fresh constrained container; no network; read-only bundle/root; no app secrets passed to run | Verify the container environment and mounts in a real deployment smoke test; execution images must contain no deployment credentials | Medium |
| T-EXEC-2 | Container or kernel escape compromises an execution host | Non-root process, dropped capabilities, `no-new-privileges`, resource limits, immutable images, and no Docker authority on the application host | Docker shares the execution host kernel. An escape can expose that worker's DB/HMAC/registry credentials, but it must not directly expose Clerk or application-host secrets. Patch promptly, keep default seccomp active, run no unrelated workloads, alert on anomalies, and rebuild the host after suspected compromise | High |
| T-EXEC-3 | Worker compromise uses the Docker socket for execution-host root control | Docker authority exists only on execution hosts; the Control Plane has none | Treat worker compromise as execution-host compromise. Give workers no Clerk secret, use a distinct narrow DB role, restrict shell access and VPC destinations, and rebuild rather than repair a suspected host | High |
| T-EXEC-4 | Fork bomb, memory bomb, output flood, infinite loop, or run storm denies service or raises cost | Configurable per-container CPU/memory/PID/fd/tmpfs/output/time limits; one active run per learner; bounded global capacity; per-host concurrency; run rate limits | Prove the declared pool with the named normal cohorts and 15/25/100-learner bursts: ten-second p95 starts for cohorts and thirty seconds for bursts, with 30/60-second maximums respectively. Monitor OOMs, queue age, disk, CPU, worker health, and spend; add execution hosts instead of removing isolation | Medium |
| T-EXEC-5 | Learner code exfiltrates data over the network | `--network none`; no credentials in the run; bundle contains only one learner/challenge snapshot | DNS/network absence must be verified from both execution images. Output remains an intentional channel back to the same learner | Low |
| T-EXEC-6 | Candidate tampers with the test process or its report to obtain a false green | Tests/config are read-only in the submitted overlay and scoring is normalized | Candidate code and tests share a container/process trust domain. Treat scores as practice feedback, not certification; design a trusted supervisor before scores gain external value | Medium |
| T-EXEC-7 | Orphaned or stale worker publishes a late result over newer state | Durable claims, heartbeats, fenced leases, atomic completion | Exercise worker-kill, lease-expiry, duplicate-worker, and host-reboot drills in staging | Low |

### Product-content protection

| ID | Threat and impact | Existing control | Residual risk / required treatment | Risk |
|---|---|---|---|---:|
| T-CONTENT-1 | Anonymous scraper downloads the challenge bank | Entire Hosted API requires a verified Clerk session; catalog contains summaries only | Prove the deployed edge cannot reach an unauthenticated alternate port or Local Mode process | Low |
| T-CONTENT-2 | Authorized learner automates sequential content extraction | 120 content reads/minute, 20 distinct challenges/hour, five solutions/hour, durable cross-replica counters, security event on bulk access | Limits slow extraction; they do not prevent patient scraping. Alert and revoke accounts that show systematic extraction | Medium |
| T-CONTENT-3 | Learner retrieves all solutions | Per-learner solved/spoiled gate plus solution rate limit | A learner may intentionally spoil and copy up to the limit. Preserve the learning tradeoff; consider canary markers only if they do not harm challenge quality | Medium |
| T-CONTENT-4 | Multiple accounts collude to bypass per-user limits | Global capacity limits, durable per-account counters, and structured security events | Monitor correlated extraction and run behavior without collecting invasive learner content; add account-creation friction or network-level controls if observed | High until monitored |
| T-CONTENT-5 | Content leaks from repository, image registry, CI artifact, backup, or operator machine | Private access can be applied outside the app; immutable releases aid attribution | Confirm repository/package visibility matches the business decision; limit collaborator/package access; ensure backups and image layers do not unintentionally publish solutions | High until verified |

### Network, availability, and operations

| ID | Threat and impact | Existing control | Residual risk / required treatment | Risk |
|---|---|---|---|---:|
| T-NET-1 | Direct access to FastAPI bypasses Caddy policy, or direct database access bypasses application authorization | Hosted launcher requires explicit trusted proxy CIDRs and rejects wildcard trust; deployment design keeps PostgreSQL on the private VPC | Only the application firewall may publish 80/443. Verify 8000, 5432, Docker, workers, and Run Bundles are unreachable publicly; permit worker-to-database traffic only from the execution-worker firewall/tag and require TLS | High until deployed |
| T-NET-2 | DDoS or request/run flood exhausts the application host or execution pool before application limits run | Authenticated application limits, one active run per learner, and bounded global run capacity | Configure Cloudflare/edge limits, connection/body limits, queue-age and worker-capacity alerts, timeouts, and DigitalOcean spend alerts; rehearse temporary deny/block response | High until deployed |
| T-NET-3 | PostgreSQL loss or corruption destroys learner state and audit evidence | Durable database and explicit migrations | Create encrypted off-host logical backups and prove restoration into a disposable database before invites | High until proven |
| T-OPS-1 | Secret appears in source, logs, shell history, screenshots, or local files | Secret-file support, ignored `.env*`, redacted application errors | Rotate on any exposure; scan Git history and images; mount production secrets read-only; document owners and rotation intervals | High until proven |
| T-OPS-2 | Security events are emitted but never collected or acted upon | Bounded one-line JSON events and durable mutation audits | Configure an external collector, retention, alert thresholds, on-call destination, and a test event before beta | High until deployed |
| T-OPS-3 | Compromised backup or log sink leaks learner data | Pseudonymized security subjects and bounded fields | Encrypt backups in transit/at rest, restrict credentials, test access, and keep the HMAC key separate from exported logs | Medium |
| T-OPS-4 | Health endpoint leaks topology or gives false rollout confidence | Separate live/ready/release contracts and bounded release data | Expose only necessary health routes; promotion must require the exact commit and execution digests, not generic HTTP 200 | Low |

### Supply chain and release integrity

| ID | Threat and impact | Existing control | Residual risk / required treatment | Risk |
|---|---|---|---|---:|
| T-SUPPLY-1 | Mutable or substituted image executes unreviewed code | Digest-pinned bases/execution images, no runtime pull, archive/digest verification, immutable commit tags | Deployment must consume release-manifest digests, verify attestations where available, and never deploy `latest`, `staging`, or `production` as the recorded immutable identity | Medium |
| T-SUPPLY-2 | Dependency or base-image vulnerability compromises a component | CI scans fixable high/critical findings, SBOMs, minimal runtime images, package managers removed | Define patch SLA and expiry-owner process for scanner exceptions; alert when the current production digest is superseded for security | Medium |
| T-SUPPLY-3 | Unauthorized promotion or partial rollout breaks release consistency | Protected GitHub Environments, serialized four-image promotion, exact release readiness, automatic tag restoration | Configure required reviewers/no self-review and bootstrap a complete rollback set before first promotion | High until configured |
| T-SUPPLY-4 | GitHub, GHCR, cloud deploy credential, or maintainer account is compromised | Short-lived Actions credentials and pinned Actions | Require MFA/passkeys, least privilege, branch protection, secret scanning, and periodic access review across every control plane | Medium |

## Required launch gates and evidence

Every row must have an owner, a date, and a durable evidence link or artifact. A verbal
confirmation is not sufficient.

### Evidence snapshot on 2026-09-10

- The GitHub repository was verified as **private** through the GitHub API.
- GHCR package visibility could not be verified with the current token because it lacks
  `read:packages`; treat package privacy as unproven until G-9 records it.
- `backend/.env.local` is ignored and not tracked, but it contains a development Clerk
  secret. That secret must be rotated after its accidental exposure during this review.
- The repository contains no production Compose manifest or Caddyfile yet, so network,
  header, port, and edge-control claims remain unproven.
- PostgreSQL schema version 7 and migrations `001` through `007` are the current
  application contract.
- The Clerk/Google configuration was exercised manually through the hosted Account
  Portal, but the deployed MakeItGreen origin does not exist yet. G-1 still requires
  end-to-end tests through that origin.
- The owner accepted the unavoidable manual-copy/content-collusion limitation for an
  invite-only beta and rejected a shared application/execution host. The current
  deployment baseline therefore requires a separate execution pool.
- Container memory is configurable and an executable named cohort/burst capacity probe
  exists in the repository, but no real-host capacity evidence has been recorded yet.

| Gate | Requirement | Passing evidence | Status |
|---|---|---|---|
| G-1 Identity | Production Clerk uses Open access, Google OAuth, exact authorized origins, locally verified session tokens, and documented revocation | Screenshots/export of settings; deployed 401/200 tests; new-account and session-revocation drills | Partially complete; open-access deployment test pending |
| G-2 Secrets | Production secrets are mounted/injected, absent from Git/images/logs, independently rotatable, and operator accounts use MFA | Secret scan; mount/permission check; rotation record for Clerk, DB, HMAC, GHCR/deploy credentials | Open; rotate exposed development Clerk secret |
| G-3 Network | Only application-host Caddy 80/443 is public; SSH is IP-restricted; backend, private-VPC database, Docker, workers, and Run Bundles are unreachable publicly | External scans of every host plus VPC/TLS, host/Compose, and firewall configuration capture | Open |
| G-4 Edge | TLS, HSTS, CSP, MIME/referrer/frame policies, body/connection limits, and edge rate/DDoS controls are active | Header scan, TLS scan, oversized/chunked request test, rate-limit test | Open |
| G-5 Database | Migrations through schema version 7 use a DDL owner; API and worker use separate least-privilege roles; PostgreSQL is private-VPC-only with TLS | Role/grant query output, schema-version output, worker TLS connection proof, and external connectivity test | Open |
| G-6 Execution | Separate execution hosts run both digest-pinned runtimes with configurable memory and pass isolation, no-network, resource-limit, timeout, orphan-cleanup, and named cohort/burst capacity checks | Python/Node adversarial smoke artifact plus capacity JSON showing challenge mix, global limit, worker count/concurrency, zero rejection/loss, and passing per-scenario p95 starts | Open |
| G-7 Recovery | Encrypted off-host PostgreSQL backup and whole-host backup exist; restore succeeds in a disposable environment | Timestamped restore drill with row counts and application readiness | Open |
| G-8 Detection | JSON security logs leave the application and worker hosts; alerts cover auth denials, scraping, rate/capacity exhaustion, readiness, expected worker-count loss, OOM, disk, queue age, and backup failure | Test events received at the alert destination and acknowledged | Open |
| G-9 Release | Four exact scanned/attested image digests are deployed consistently across the application host and every execution host; protected promotion and complete rollback work | Release manifest, per-host rollout record, `/health/release`, expected worker-count check, and rollback drill | Open |
| G-10 Beta operations | Named testers, support/incident contact, privacy/retention notice, account-revocation procedure, spend alert, one-active-run-per-user policy, and one-week capacity review are defined | Owner-approved beta checklist, incident tabletop, and capacity evidence meeting every named cohort/burst SLO | Open |

## Minimum adversarial staging tests

Run these through the public HTTPS origin, not directly against a developer process,
except for the explicitly identified direct staging capacity probe:

1. No token, malformed token, and wrong authorized party return 401 and never
   create learner state; a valid newly created account reaches the API.
2. Ending a user's Clerk sessions blocks the next request.
3. User A cannot read, mutate, restore, reset, spoil, debrief, or poll User B's data or
   Run Job ID.
4. Encoded traversal, symlink overlays, protected test/config writes, and unauthorized
   new paths fail before a Run Bundle is staged.
5. Python and Node submissions attempt outbound TCP/DNS, fork/process floods, memory
   exhaustion, disk/tmpfs exhaustion, output flooding, and timeout descendants.
6. Killing a worker mid-run, starting a replacement, and later reviving the old worker
   cannot publish two results or overwrite newer state.
7. Crossing content, distinct-challenge, solution, mutation, run, and capacity limits
   returns 429, persists bounded audit evidence, and produces the expected alert.
8. Public scans cannot reach ports 8000 or 5432, the Docker API, the worker, or a Run
   Bundle path. A Challenge Run container cannot reach PostgreSQL, Caddy, metadata
   services, or the Internet.
9. A database outage makes readiness and request admission fail closed; recovery does
   not lose tenant boundaries or operation fences.
10. Restore the latest logical backup into a disposable database, start matching API
    and worker digests, and complete one Python and one Node practice loop.
11. Promote a known release, verify exact-version readiness, then roll back all four
    components and verify the recorded digest set.
12. Render hostile Markdown, file names, test messages, and output; verify they remain
    text and that the deployed CSP blocks unexpected script execution.
13. On disposable staging, run `scripts/execution_capacity_probe.py` for the defined
    `small-burst`, `cohort-50`, `cohort-100`, `peak-burst-100`, and `retry-burst`
    workloads across the default Python/Node challenge mix. Record the global limit,
    worker count, per-host concurrency, per-run memory, rejection/completion counts,
    and per-scenario p95/maximum start times; then complete one small run through the
    public API to cover the HTTP path.

## Incident priorities

1. **Contain execution:** stop or isolate the affected execution worker, then block new
   Run Jobs if container escape, Docker abuse, or host compromise is suspected.
2. **Contain identity:** revoke the learner's beta metadata and Clerk sessions for
   account abuse; rotate Clerk/Google credentials if provider configuration may be
   exposed.
3. **Preserve evidence:** snapshot relevant audit rows, external security logs, release
   digests, host events, and Cloudflare logs without copying learner source into general
   logs.
4. **Rotate by boundary:** assume a host compromise exposes the worker database/HMAC
   secrets and any host registry credential. Assume Control Plane compromise exposes
   Clerk, database, and HMAC secrets. Rotate affected credentials independently.
5. **Recover immutably:** redeploy a known attested digest set onto a clean host; do not
   repair a suspected-compromised host in place.
6. **Notify and learn:** notify affected beta users when their account or content may
   have been exposed, record the root cause, and add a regression or deployment check.

## Accepted limitations and review triggers

The owner must review this model again before any of the following:

- allowing anonymous API access or adding a new enrollment/authorization gate;
- exceeding the tested per-host concurrency or changing the worker trust/network
  boundary;
- placing unrelated workloads on the execution host;
- adding a new language, runtime, dependency-install path, file upload/archive import,
  preview renderer, or networked challenge;
- moving PostgreSQL, the worker, or Run Bundle storage across hosts/providers;
- making scores externally meaningful or adding competitive rankings;
- adding organization/team sharing, administrative APIs, billing, or AI features;
- changing authentication providers, custom claims, session duration, domains, or
  frontend token storage;
- exposing challenge or solution content through a new endpoint, cache, artifact, or
  analytics system;
- a material security incident, dependency compromise, or container-runtime advisory.

## Owner review record

| Decision | Owner | Date | Notes |
|---|---|---|---|
| Accept manual-copy/content-collusion limitation for invited beta | Oluwatosin | 2026-09-10 | Accepted for the invite-only beta; bulk extraction remains rate-limited and monitored |
| Require separate execution hosts for invited beta | Oluwatosin | 2026-09-10 | Accepted; no Docker authority or Challenge Runs on the application host |
| Approve beta launch after gates G-1 through G-10 pass | Pending | Pending | No public traffic before approval |
| Replace invite-only enrollment with authenticated self-service registration | Oluwatosin | 2026-09-28 | Remove the custom `beta_access` gate; retain Clerk authentication, tenant isolation, durable admission, global capacity, content limits, and worker isolation |
