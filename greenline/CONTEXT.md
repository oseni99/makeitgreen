# MakeItGreen

MakeItGreen is a repository-based interview-practice platform that supports a trusted personal workflow and is being hardened for untrusted hosted use.

## Language

**Runtime Mode**:
The mandatory startup classification that selects either **Local Mode** or **Hosted Mode**.
_Avoid_: environment, deployment type

**Local Mode**:
The trusted personal-development mode that may use optional identity, local state, and host subprocess execution.
_Avoid_: development mode, unsafe mode

**Hosted Mode**:
The untrusted-user mode that must fail startup unless every production safety requirement is configured.
_Avoid_: production mode, cloud mode

**Control Plane**:
The public Hosted Mode API process that authenticates requests, mutates durable state, and enqueues Run Jobs. It has no Challenge Run execution authority or Docker access.

**Execution Worker**:
The non-HTTP Hosted Mode process that claims durable Run Jobs and is the only application process given Docker execution authority.

**Challenge Run**:
One execution of a learner's workspace against a challenge's declared tests, producing streamed output and a normalized result.
_Avoid_: attempt, test process

**Run Bundle**:
The validated, user-scoped snapshot of challenge source and learner edits supplied read-only to an isolated Challenge Run.
_Avoid_: volume, checkout

**Learner Challenge State**:
The tenant-scoped aggregate containing one learner's workspace overlays, progress, and Challenge Run history for one challenge.
_Avoid_: user files, progress database

**Learner Profile**:
The tenant-scoped preferences that follow one learner across devices, currently their selected Prep Path.
_Avoid_: browser setting, local preference

**Prep Path**:
A learner-selected curriculum that recommends the next challenge without hiding the full catalog.
_Avoid_: course enrollment, mandatory track

**Learning Debrief**:
The short post-solve explanation of root cause, why the fix works, and its tradeoff, paired with a usefulness rating and optional product comment.
_Avoid_: solution notes, AI interview

**Product Event**:
A bounded first-party learning-loop milestone used for aggregate beta measurement; it never contains source code, debrief text, or the optional product comment.
_Avoid_: Audit Event, analytics payload

**Run Job**:
The durable queued, running, or terminal lifecycle that schedules one Hosted Mode Challenge Run and exposes bounded incremental output.
_Avoid_: background thread, run record

**Operation Lease**:
The time-bounded, monotonically fenced authority to mutate one Learner Challenge State while its Run Job is active.
_Avoid_: mutex, lock row

**Request Admission**:
The Hosted Mode decision that applies a learner's request budget and durably records the request before application mutation begins.
_Avoid_: middleware check, throttle call

**Audit Event**:
The durable, tenant-scoped lifecycle record for one admitted mutation or the first rate-limited request in a learner/scope/window, using bounded action names and no request body or file path.
_Avoid_: application log, access log

**Runtime Readiness**:
The current ability of one Hosted Mode process role to perform its own work: the Control Plane can reach its PostgreSQL Adapters, or an Execution Worker can also reach its container daemon, immutable images, and shared Run Bundle storage.
_Avoid_: process health, startup complete

**Secret Source**:
Exactly one direct environment value or absolute mounted file from which Hosted Mode reads a sensitive value without logging it.
_Avoid_: config string, credential variable

**Trusted Proxy**:
An explicitly allowlisted IP network permitted to supply forwarded client and protocol headers to the supported production launcher.
_Avoid_: load balancer header, proxy mode

**Security Event**:
A collector-ready JSON record with a server request ID, bounded action/status fields, severity, and an HMAC-pseudonymized learner subject.
_Avoid_: Audit Event, print statement

## Relationships

- A **Runtime Mode** is exactly one of **Local Mode** or **Hosted Mode**.
- **Hosted Mode** requires stricter identity, execution-isolation, and durable-state guarantees than **Local Mode**.
- An **Execution Worker** must refuse startup when isolated execution is unavailable; no Hosted Mode role may fall back to host subprocess execution.
- **Hosted Mode** must refuse startup unless Clerk authentication has both a secret key and a non-empty authorized-party allowlist.
- **Hosted Mode** must refuse startup while learner state depends on local filesystem or SQLite storage.
- A **Challenge Run** uses host subprocess execution only in **Local Mode**.
- An isolated **Challenge Run** receives exactly one read-only **Run Bundle** and copies it into a bounded ephemeral workspace.
- In **Hosted Mode**, **Learner Challenge State** is stored transactionally in PostgreSQL and a **Run Bundle** is materialized from one validated workspace snapshot.
- In **Hosted Mode**, a **Run Job** durably owns one **Operation Lease** for its learner-and-challenge scope from enqueue through terminal persistence.
- A worker may publish output or a result only while its claim token and **Operation Lease** fence still match; recovered or superseded workers cannot mutate state.
- Completing a **Run Job** atomically records Challenge Run history, updates progress, makes the job terminal, and releases its **Operation Lease**.
- A **Learner Profile** keeps the selected **Prep Path** consistent across authenticated sessions while the catalog remains fully browsable.
- A **Learning Debrief** may be saved only after the learner solves that challenge and is removed when its Learner Challenge State is reset.
- A **Product Event** records only bounded milestones; **Audit Events** remain the security/accountability record for admitted mutations.
- In **Hosted Mode**, every authenticated application request passes **Request Admission** before reaching a route.
- **Request Admission** creates an **Audit Event** before any mutation and refuses the request when durable admission is unavailable.
- **Run Job** enqueue atomically enforces global and per-learner active-run capacity across replicas.
- **Runtime Readiness** is distinct from process liveness and is evaluated against only the dependencies owned by that process role.
- The **Control Plane** never receives a Docker socket, Docker CLI, or container execution Adapter and remains ready independently of worker capacity.
- An **Execution Worker** refuses startup unless the container daemon is reachable and both digest-pinned execution images are already present without pulling.
- Hosted Mode accepts each sensitive value from exactly one valid **Secret Source**.
- Only a **Trusted Proxy** may influence forwarded request metadata; wildcard trust and direct Hosted startup are refused.
- **Security Events** complement durable **Audit Events**: they support operational collection and alerting without exposing raw learner identity or request content.

## Example dialogue

> **Developer:** “Can a missing Clerk secret make the application start without authentication?”
> **Domain expert:** “Only in **Local Mode**. **Hosted Mode** must refuse to start when a required safety setting is missing.”

## Flagged ambiguities

- “production” previously described both an optimized build and public untrusted hosting; **Hosted Mode** refers specifically to the latter.
