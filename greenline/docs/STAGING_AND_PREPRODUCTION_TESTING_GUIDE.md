# MakeItGreen staging and pre-production testing strategy

**Status:** proposed next engineering approach; not yet implemented.

This document explains how MakeItGreen should test complete releases before
they reach real users. It exists because Local Mode and Hosted Mode do not
exercise the same system boundaries, and production must not be the first place
where those boundaries are tested together.

The goal is not to make a developer laptop identical to production. That is
neither realistic nor necessary. The goal is to test progressively, then run
the exact production artifacts in a safe environment whose architecture
matches production closely enough to expose integration failures.

## 1. The problem this strategy solves

The hosted pytest-output incident demonstrated an important gap.

Local Mode used approximately this path:

```text
Browser -> local backend -> local pytest process -> result
```

Production Hosted Mode used this path:

```text
Browser
  -> Caddy
  -> Control Plane
  -> PostgreSQL Run Job
  -> remote Execution Worker
  -> Docker execution container
  -> Execution Worker
  -> PostgreSQL output updates
  -> Control Plane polling
  -> Browser result panel
```

The failure existed in the worker-to-PostgreSQL streaming path. Local Mode
bypassed that path, so a successful local manual test could not prove that
Hosted Mode worked.

This does not mean local testing is bad. It means each testing layer proves a
different contract.

## 2. The four environments

| Environment | Primary purpose | What it should prove |
|---|---|---|
| Local development | Fast feedback | Individual behavior and developer workflow |
| CI | Repeatable automated verification | Source correctness and runnable release images |
| Staging | Production-shaped release rehearsal | Complete hosted workflows across real boundaries |
| Production | Serve real users | The already-tested release rolled out correctly |

Production health checks are still necessary, but production should confirm a
deployment rather than discover whether its basic workflow works.

## 3. The target staging architecture

Staging should reproduce the production topology:

```text
staging.makeitgreen.dev
          |
        Caddy
          |
  staging Control Plane
          |
  staging PostgreSQL
          |
     private network
          |
 staging Execution Worker
          |
 worker-host Docker daemon
          |
 disposable execution container
```

The preferred shape is two small staging hosts:

1. One application host for Caddy, the Control Plane, and PostgreSQL.
2. One worker host for the Execution Worker and disposable Run containers.

Keeping the hosts separate tests the same trust and network boundary used in
production. A cheaper single-host staging system can be useful temporarily,
but it cannot fully prove private networking, firewall behavior, or cross-host
database TLS.

## 4. What must match production

Staging and production should use the same:

- Dockerfiles and built container images;
- immutable image digests;
- application and worker Compose files;
- application/worker host separation;
- PostgreSQL major version and migration set;
- database-role and grant model;
- Caddy routing and security-header policy;
- PostgreSQL TLS verification;
- worker-to-database network path;
- secret file names, mounts, owners, and modes;
- health checks;
- worker Run Bundle and Docker-socket behavior;
- resource and security controls such as read-only filesystems, dropped
  capabilities, memory limits, and PID limits;
- release-health contract tying the Control Plane and workers to one source
  commit and execution-image set.

This set of requirements is the **parity contract**. A change to any production
boundary should normally be exercised through the equivalent staging boundary.

## 5. What must remain separate

Staging must not reuse production state or authority.

| Concern | Staging | Production |
|---|---|---|
| Domain | `staging.makeitgreen.dev` | `makeitgreen.dev` |
| Clerk | Dedicated test/development instance | Production instance |
| Users | Synthetic and engineering accounts | Real invited learners |
| PostgreSQL | Separate staging database and volume | Production database and volume |
| Secrets | Separate staging values | Production values |
| HMAC key | Staging-only key | Production-only key |
| Backups | Test data; safe restore target | Protected production backups |
| Logs and alerts | Clearly labelled staging | Production destinations |

Never copy production Clerk secrets, database credentials, learner records, or
private logs into staging. If realistic data is needed later, generate
synthetic records or use an explicitly designed anonymization process.

## 6. Build once, promote the same artifact

The release must move through environments without being rebuilt:

```text
commit
  -> CI tests source
  -> CI builds four images
  -> CI scans and smoke-tests those images
  -> CI publishes immutable digest references
  -> deploy those exact digests to staging
  -> staging acceptance tests pass
  -> deploy the same digests to production
```

The four release images are:

- Control Plane;
- Execution Worker;
- Python execution image;
- Node execution image.

Rebuilding for production would create a new artifact, even if the source
commit were unchanged. Dependencies, base images, build tooling, or timestamps
could differ. The staging evidence applies only to the digests that staging
actually ran.

## 7. The release gates

### Gate A: local developer checks

Before pushing a change, run the relevant focused tests and then the complete
local suites:

```bash
cd greenline/backend
venv/bin/python -m pytest -q

cd ../frontend
npm test
npm run lint
npm run build
```

For production-only behavior, add a deterministic local regression using a
fake slow dependency, failure injection, or a controlled subprocess. The test
should reproduce the contract, not merely copy the implementation.

### Gate B: pull-request CI

The existing MakeItGreen workflow already provides important protection:

- backend tests;
- challenge validation;
- frontend tests, lint, and build;
- construction of the real runtime images;
- vulnerability scanning;
- PostgreSQL migrations;
- Control Plane and worker health checks;
- isolated Python and Node execution-image checks;
- a real challenge execution through the worker container boundary;
- SBOM and provenance generation.

Every required job must pass before a release is eligible for staging.

### Gate C: immutable release publication

After the protected branch passes CI, publish one release manifest containing
the exact four image digests and source commit. Do not manually assemble image
references from different workflow runs.

### Gate D: staging deployment

Deploy the candidate manifest to staging in this order:

1. Validate deployment configuration.
2. Back up staging if its state is useful.
3. Pull all candidate images.
4. Start or update PostgreSQL safely.
5. Apply required migrations and runtime grants.
6. Update the worker.
7. Update the Control Plane and Caddy.
8. Wait for `/health/live`, `/health/ready`, and `/health/release`.
9. Confirm the reported source SHA and execution-image digests exactly match
   the candidate manifest.

### Gate E: automated staging acceptance

An automated browser and API test must exercise Hosted Mode, not Local Mode.
At minimum, it should:

1. Sign in with a dedicated staging test account.
2. Open the challenge catalog.
3. Open a known Python challenge.
4. Confirm its files and instructions load.
5. Edit a writable file and confirm autosave.
6. Submit a Run Job.
7. Observe a small output marker while the execution is still running.
8. Confirm output offsets are ordered with no missing or duplicated text.
9. Confirm the completed output includes pytest's final summary.
10. Confirm structured pass/fail totals agree with the textual result.
11. Refresh and confirm the workspace and Run history persist.
12. Apply a known passing solution and confirm the challenge becomes solved.
13. Repeat a smaller equivalent workflow for a Node challenge.

The streaming test is essential. A test that waits only for the final status
would not catch delayed live output, while a test that watches only incremental
output would not prove that the authoritative final report is complete.

### Gate F: focused human exploration

Automation should cover repeatable contracts. A human release check should
focus on changed or risky behavior, such as:

- authentication and invitation flow changes;
- editor behavior in multiple browsers;
- mobile or narrow layouts;
- error and recovery messages;
- long-running or high-output challenges;
- changes to deployment, networking, database permissions, or secrets.

This is not an invitation to retest the entire product manually. The checklist
should be risk-based and short enough that engineers actually follow it.

### Gate G: production promotion

Only after staging passes should the exact candidate digests be approved for
production. The promotion record must identify:

- source commit;
- four image digests;
- staging acceptance result;
- approving person or workflow;
- promotion time;
- previous production digests for rollback.

### Gate H: production rollout confirmation

After deployment, run a deliberately small confirmation:

- `/health/live` returns live;
- `/health/ready` returns ready;
- `/health/release` reports the expected commit and worker image set;
- one controlled synthetic Hosted Mode run completes;
- error rate, worker health, PostgreSQL health, and resource use remain normal.

If these checks fail, roll back to the previous known-good digest set. Do not
debug an unstable new release while leaving it exposed to users when a safe
rollback is available.

## 8. Tests specifically required by the streaming incident

The following contracts must be protected at different levels.

### Runner regression tests

- A slow persistence callback cannot truncate authoritative output.
- Small output followed by silence is published before process completion.
- Streamed output remains ordered.
- Final output contains the last marker and pytest summary.
- Very loud output stays within the configured memory and tail limits.
- Timeout cleanup still terminates descendant processes.

### Hosted integration test

- Create a durable Run Job through the same interface used by the browser.
- Let a real worker claim it from PostgreSQL.
- Run it in the pinned execution container.
- Poll output through the Control Plane.
- Verify incremental and final output separately.
- Verify the saved Run history matches the completed result.

### Browser staging test

- Authenticate through the staging identity provider.
- Exercise the editor, autosave, Run button, live result pane, completion
  summary, refresh, and history.

Together, these tests cover the unit contract, distributed backend contract,
and user-visible contract.

## 9. Observability required in staging

Staging tests are much easier to diagnose when one Run Job can be followed
across components. Logs and records should share identifiers such as:

- Run Job ID;
- user or synthetic-test ID;
- challenge slug;
- worker ID;
- source SHA;
- image digest;
- claim fence or token where safe to log;
- start, claim, first-output, completion, and failure timestamps.

Useful measurements include:

- time from submission to worker claim;
- time from claim to first output;
- time from first output to completion;
- number and size of output batches;
- execution duration;
- terminal-output truncation flag;
- worker heartbeat age;
- database errors and connection latency;
- container exit code and resource termination reason.

Secrets, database URLs, source submissions, and authentication tokens must not
be written to ordinary diagnostic logs.

## 10. Staging data lifecycle

Staging must be safe to reset. Establish explicit rules:

- synthetic accounts are identifiable;
- test Run Jobs and workspaces may be deleted on a schedule;
- migrations are still applied exactly as production expects;
- destructive migration rehearsals use a staging backup first;
- restore drills never target production;
- automated tests clean up what they create when practical;
- failed cleanup cannot delete outside a narrowly resolved staging scope.

Staging is disposable as an environment, but migration and recovery behavior
must still be realistic.

## 11. Initial implementation plan

### Phase 1: close the immediate CI gap

- Keep the two runner streaming regressions required.
- Extend the image smoke test to cover durable Run Job output streaming through
  PostgreSQL and the worker.
- Assert both incremental delivery and complete final output.
- Make this test a required CI gate.

### Phase 2: provision staging

- Create isolated staging app and worker hosts in one private network.
- Add staging DNS and TLS.
- Create a staging Clerk instance and synthetic invited account.
- Create staging-only secrets and database storage.
- Reuse the checked-in Compose and validation tooling.
- Configure the protected GitHub `staging` environment.
- Configure staging health and rollback targets.

### Phase 3: automate staging deployment

- Read image digests from one successful release manifest.
- Deploy those exact digests without rebuilding.
- Apply migrations and grants in a controlled step.
- Wait for exact-version release health.
- Store deployment evidence and previous digests.

### Phase 4: automate staging acceptance

- Add the authenticated browser journey.
- Add Python and Node Hosted Mode runs.
- Add live-stream and final-result assertions.
- Save screenshots, traces, logs, and Run Job IDs on failure.
- Block production promotion unless acceptance passes.

### Phase 5: make production a promotion

- Promote the already-tested digest set.
- Run minimal production confirmation checks.
- Monitor a short rollout window.
- Automatically restore the previous digest set if exact-version health fails.

## 12. Release decision checklist

A release is eligible for production only when every answer is **yes**:

- Did focused and full local tests pass?
- Did all required CI jobs pass?
- Were all four images built once and identified by digest?
- Did the image-level Hosted Mode smoke test pass?
- Did staging run those exact digests?
- Did staging report the expected source SHA and worker release?
- Did the authenticated Hosted Mode browser journey pass?
- Were live output and complete final output both verified?
- Were migrations and runtime grants verified?
- Is a known-good rollback digest set recorded?
- Are staging and production secrets and data isolated?
- Is the production change approved?

If any answer is no, the default decision is not to promote.

## 13. The mental model to remember

```text
Local proves behavior quickly.
CI proves the source and images repeatedly.
Staging proves the complete release safely.
Production confirms the tested release was deployed correctly.
```

No single layer is enough. Confidence comes from overlapping tests, with each
layer covering boundaries that the layer before it cannot reproduce.
