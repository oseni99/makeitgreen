# MakeItGreen production operations: keeping the system safe after deployment

This is the companion to the [production deployment session guide](PRODUCTION_DEPLOYMENT_SESSION_GUIDE.md). The first guide explains how MakeItGreen reached production. This guide explains how to keep it reliable, recover it after failures, and change it without losing control. The proposed next release path is documented separately in the [staging and pre-production testing strategy](STAGING_AND_PREPRODUCTION_TESTING_GUIDE.md).

It is written for a developer who has deployed an application but is new to operating production systems.

It has five goals:

1. Explain the difference between a successful deployment and a reliable service.
2. Identify what MakeItGreen must preserve, monitor, rotate, and recover.
3. Teach a safe way to respond when something fails.
4. Turn future deployments into repeatable, observable operations.
5. Provide a reading and practice plan that does not require learning everything at once.

This document describes operating principles and proposed next work. It does **not** claim that every backup, alert, or automation described here already exists. Items marked **current** were observed in the repository or deployment session. Items marked **next** are work still to implement and verify.

Never put real passwords, private keys, tokens, database URLs, or secret contents in this document, Git, screenshots, shell history, or issue trackers.

---

## 1. The new mental model: deployment starts the operating phase

A deployment answers:

> Can this version start and serve the intended user journey now?

Production operations answer:

> Can we detect failure, preserve data, restore service, make safe changes, and explain what happened tomorrow?

Those are different promises.

```text
Build it
   |
   v
Deploy it -------> Verify the real user journey
   |                         |
   v                         v
Observe it <------ Detect unexpected behavior
   |
   v
Recover it ------> Restore data and service
   |
   v
Learn from it ---> Improve automation and prevention
```

The system is not finished merely because all containers say `healthy`. Containers, hosts, credentials, disks, networks, cloud accounts, and people change over time. Operations is how you keep those changes from becoming surprises.

### The six contracts of a reliable service

Think of production as six contracts:

| Contract | Question it answers |
|---|---|
| Availability | Can users reach the service? |
| Correctness | Does it return the right result? |
| Durability | Will important data survive a failure? |
| Security | Can only intended identities perform intended actions? |
| Recoverability | Can we restore service and data within an acceptable time? |
| Explainability | Do logs and records tell us what happened? |

Your first deployment provided strong evidence for availability, correctness, and several security boundaries. The next phase must add stronger evidence for durability, recovery, and long-term explainability.

---

## 2. Current state versus next operational work

### What the deployment has already proven

**Current:**

- The app, PostgreSQL, Caddy, and worker containers start and report healthy.
- Public health endpoints return successful responses over HTTPS.
- `/health/release` sees one live worker on the matching source release.
- The application renders the Monaco editor and can run tests.
- PostgreSQL is not reachable through the app server's public IP.
- The worker exposes no public application or Docker API port.
- The app and worker use immutable digest-pinned images.
- The worker runs learner code inside fresh, constrained containers.
- Database runtime roles are separated from the schema owner.
- Host-specific secrets are stored with restricted ownership and modes.

This is meaningful evidence. It proves that a specific version worked through the intended path at a specific time.

### What has not yet been proven

**Next:**

- Automatic database backups run on schedule.
- Backups are copied away from the app Droplet.
- A clean machine can restore a backup successfully.
- Restore time and acceptable data loss have been measured.
- External monitoring alerts someone when the site or worker is unhealthy.
- Logs survive container replacement and are searchable centrally.
- Disk, memory, CPU, and queue saturation generate alerts.
- Secret rotation has a tested procedure.
- Infrastructure can be recreated from version-controlled definitions.
- The team has rehearsed app-host, worker-host, and database failures.

The phrase “not yet proven” is deliberate. Never infer recovery from the existence of a backup file, or monitoring from the existence of a health endpoint. Recovery requires a restore test; monitoring requires an external system that checks and notifies.

---

## 3. Read this before changing production operations

Study these subjects in order. You do not need to finish every document before doing any work; read enough to understand the next controlled task.

### Stage 1: reliability language

Learn:

- **failure:** a component can no longer perform its responsibility;
- **incident:** a failure is harming, or risks harming, users;
- **availability:** the fraction of time a service is usable;
- **SLI:** a measured indicator such as successful ready checks;
- **SLO:** the target for an SLI;
- **RPO:** the maximum acceptable amount of data loss measured in time;
- **RTO:** the target time to restore service;
- **MTTR:** average time to recover from incidents.

Start with:

- [Google SRE: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Google SRE: Monitoring distributed systems](https://sre.google/sre-book/monitoring-distributed-systems/)

Do not choose tools before choosing what failure must be detected and how quickly.

### Stage 2: PostgreSQL backup and recovery

Learn:

- logical dumps with `pg_dump` and `pg_restore`;
- cluster-wide role metadata with `pg_dumpall` where appropriate;
- physical base backups;
- Write-Ahead Log (WAL);
- point-in-time recovery (PITR);
- backup retention, encryption, and integrity verification;
- why a restore exercise is the real backup test.

Start with:

- [PostgreSQL 17: Backup and restore](https://www.postgresql.org/docs/17/backup.html)
- [PostgreSQL 17: SQL dump](https://www.postgresql.org/docs/17/backup-dump.html)
- [PostgreSQL 17: `pg_restore`](https://www.postgresql.org/docs/17/app-pgrestore.html)
- [PostgreSQL 17: Continuous archiving and PITR](https://www.postgresql.org/docs/17/continuous-archiving.html)

PostgreSQL documents three broad approaches: SQL dumps, file-system-level backups, and continuous archiving. They solve different recovery problems.

### Stage 3: cloud-host recovery

Learn:

- Droplet backups versus manual snapshots;
- restoring a Droplet versus restoring an application database;
- regional failure and account-level failure;
- VPC, firewall, reserved IP, and DNS dependencies;
- how infrastructure-as-code recreates resources.

Start with:

- [DigitalOcean Droplet backups](https://docs.digitalocean.com/products/backups/)
- [DigitalOcean Droplet snapshots](https://docs.digitalocean.com/products/snapshots/)
- [DigitalOcean Monitoring](https://docs.digitalocean.com/products/monitoring/)
- [DigitalOcean Terraform provider](https://docs.digitalocean.com/reference/terraform/)

A whole-Droplet backup is useful, but it is not automatically a database-consistent, portable, frequently tested PostgreSQL recovery system.

### Stage 4: Docker operations

Learn:

- restart policies and health checks;
- bind mounts and named volumes;
- persistent versus ephemeral container state;
- logs and logging drivers;
- CPU, memory, PID, and disk limits;
- registry authentication;
- why Docker daemon access is privileged.

Start with:

- [Docker storage volumes](https://docs.docker.com/engine/storage/volumes/)
- [Docker Compose health checks](https://docs.docker.com/reference/compose-file/services/#healthcheck)
- [Docker logging](https://docs.docker.com/engine/logging/)
- [Docker daemon attack surface](https://docs.docker.com/engine/security/protect-access/)
- [Docker Linux post-installation](https://docs.docker.com/engine/install/linux-postinstall/)

### Stage 5: secrets and access

Learn:

- secret creation, distribution, use, rotation, revocation, and destruction;
- least privilege;
- break-glass access;
- audit trails;
- short-lived versus long-lived credentials;
- encryption at rest and in transit.

Start with:

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [GitHub: Working with the container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Clerk production checklist](https://clerk.com/docs/deployments/overview)

### Stage 6: incident response and learning

Learn:

- detection, triage, containment, recovery, and follow-up;
- incident command and communication;
- timelines and evidence preservation;
- blameless post-incident reviews;
- corrective actions with owners and deadlines.

Start with:

- [Google SRE: Managing incidents](https://sre.google/sre-book/managing-incidents/)
- [Google SRE: Postmortem culture](https://sre.google/sre-book/postmortem-culture/)

---

## 4. Know what data matters

You cannot design backups until you classify the system's data.

### Tier 1: irreplaceable production state

For MakeItGreen, PostgreSQL is the main Tier 1 asset. It contains durable learner state such as:

- workspace edits;
- challenge progress and attempts;
- run history and snapshots;
- queued and running Run Jobs;
- worker release heartbeats;
- abuse-control and audit state.

If this data disappears, rebuilding containers will not bring it back.

### Tier 2: secrets and identity material

Examples include:

- Clerk secret key;
- API and worker database URLs;
- database administrator password;
- PostgreSQL CA, server certificate, and private key;
- security-log HMAC key;
- GHCR credentials on each host;
- SSH private keys held by administrators.

These are not ordinary configuration. They need encrypted backup or a separate recoverable secret-management system. A backup of secrets must be more strongly protected than the application source code.

### Tier 3: deployment configuration

Examples:

- Compose files;
- `Caddyfile`;
- `pg_hba.conf`;
- `runtime.env` and `release.env`;
- firewall, VPC, DNS, and Droplet definitions.

Most static templates exist in Git. Host-specific values and exact active release references must still be recorded securely. Infrastructure-as-code should eventually define the cloud resources.

### Tier 4: reconstructable runtime state

Examples:

- pulled container image layers;
- control-plane and worker containers;
- Docker bridge networks;
- temporary Run Bundles;
- disposable execution containers.

These should be recreated, not backed up as precious data.

### Tier 5: useful but replaceable operational state

Examples:

- Caddy certificate/account data;
- local Docker logs;
- package caches.

Caddy can normally obtain certificates again, but preserving its data may make recovery faster and avoid certificate-authority rate limits. Logs may be essential for incident investigation even though the application does not require them to start.

### The rule

Before deleting or replacing anything, ask:

```text
Is this the recipe, a running copy, or the only copy of user data?
```

- Git and Compose files are recipes.
- Containers are running copies.
- `/srv/makeitgreen/postgres-data` currently holds the live database files.

Confusing those categories is one of the easiest ways to turn routine maintenance into data loss.

---

## 5. Backup strategy for MakeItGreen

### Backup goals come before backup commands

Choose explicit recovery targets. A reasonable beta starting proposal might be:

```text
RPO: lose no more than 24 hours of data
RTO: restore basic service within 4 hours
Retention: 7 daily + 4 weekly + 3 monthly recovery points
Restore drill: at least monthly and after backup-system changes
```

Those numbers are examples, not decisions made by this document. The product owner must decide how much data loss and downtime are acceptable. Stricter targets require more automation, storage, replication, and cost.

### Layer 1: logical PostgreSQL dumps

A logical dump describes database objects and data in a portable form. PostgreSQL states that `pg_dump` creates an internally consistent snapshot and generally does not block ordinary reads and writes.

For a small beta database, a custom-format dump is a useful first recovery layer:

```text
PostgreSQL container
      |
      | pg_dump --format=custom
      v
encrypted timestamped backup file
      |
      | copy and verify
      v
off-host object storage with retention
```

Why custom format is useful:

- `pg_restore` can inspect and selectively restore it;
- it supports flexible restore ordering;
- it is compressed by default;
- it can restore into a newly created database.

Do not invent the production backup command by copying fragments from chat. Implement a reviewed script that:

1. obtains credentials without printing them;
2. writes to a temporary file on a filesystem with sufficient space;
3. exits on every error;
4. creates a checksum;
5. encrypts the artifact;
6. uploads it to independent storage;
7. verifies that the uploaded object exists and has the expected size/checksum;
8. removes local temporary plaintext;
9. emits a success/failure metric;
10. is exercised by a restore job.

### Back up roles and global metadata

A database dump and a role definition are different things. MakeItGreen uses:

- a schema-owning administrator role;
- `greenline_api`;
- `greenline_worker`;
- privileges applied by the bootstrap script.

Recovery must recreate roles and grants without exposing their passwords. Options include:

- version-controlled idempotent role/grant SQL plus newly generated passwords;
- a protected global-object dump where appropriate;
- a secret manager that restores credentials separately.

The existing bootstrap script is useful because it makes role and grant creation repeatable. Password material must remain outside Git.

### Layer 2: point-in-time recovery

Daily dumps can lose almost a day of changes. When the product needs a smaller RPO, add PostgreSQL continuous archiving:

```text
periodic base backup + continuously archived WAL
                         |
                         v
restore to a chosen time before an accident
```

PITR is valuable when someone accidentally deletes or corrupts data at 14:03 and you need the database as it existed at 14:02. It is more operationally demanding than a daily logical dump, so introduce it only with monitoring and restore drills.

### Layer 3: Droplet backups or snapshots

DigitalOcean backups/snapshots provide another recovery layer for host-level failure or accidental host configuration loss. They can shorten the time to reconstruct a server.

They should not be the only database backup because:

- their schedule may not match the desired database RPO;
- whole-disk recovery is less portable than a PostgreSQL dump;
- application-consistent database recovery needs to be understood and tested;
- a cloud-account problem can affect both the live Droplet and its cloud-native backup.

Use host backups as defense in depth, not as a substitute for PostgreSQL-aware backups stored separately.

### The 3-2-1 idea

A useful general rule is:

- keep at least **3** copies of important data;
- on at least **2** kinds or administrative domains of storage;
- with at least **1** copy outside the production failure domain.

For example: live PostgreSQL data, an encrypted logical dump in object storage, and a separately controlled longer-retention copy.

### What not to do

- Do not copy a live `postgres-data` directory with ordinary `cp` or `tar` and assume it is consistent.
- Do not store the only backup on the same Droplet or disk as PostgreSQL.
- Do not keep unencrypted dumps containing user data indefinitely.
- Do not print passwords into logs or include database URLs in filenames.
- Do not call a scheduled job successful merely because it exited zero; verify the artifact.
- Do not wait for a real incident to attempt the first restore.

---

## 6. A restore drill is the real backup test

A backup is a claim. A restore is evidence.

### Safe restore-drill shape

Never test by overwriting the live production database. Restore into an isolated environment:

```text
production backup artifact
        |
        v
fresh isolated PostgreSQL instance
        |
        +-- verify schema version
        +-- verify role/grant procedure
        +-- count important rows
        +-- run application smoke tests
        +-- record duration and problems
        v
destroy isolated drill environment
```

### Restore acceptance checklist

A restore drill should prove:

- the selected backup can be downloaded and decrypted;
- its checksum matches;
- PostgreSQL accepts the archive;
- the expected database and schema version exist;
- required roles and grants can be recreated;
- representative learner workspaces and run history exist;
- the control plane can connect with a newly issued runtime credential;
- the application starts and passes a user-journey smoke test;
- the measured restore time is inside the RTO;
- the restored point is inside the RPO;
- the procedure is documented clearly enough for someone else to follow.

### Record evidence

For every drill, record:

```text
date
backup identifier and creation time
backup checksum
PostgreSQL version
person running the drill
start and completion times
data checks performed
problems encountered
corrective actions
```

Do not record secret values.

### Restoration versus failover

- **Restore** rebuilds state from a backup and usually involves downtime.
- **Failover** switches to an already prepared replica or redundant component.

MakeItGreen currently has a single PostgreSQL container, so database recovery is restore-oriented. High availability and automated failover would be a later architectural project, not a small configuration toggle.

---

## 7. Understand the single points of failure

A single point of failure is a component whose loss removes a system capability because no ready substitute exists.

### Failure matrix

| Failure | User-visible effect | Data risk | First recovery direction |
|---|---|---|---|
| Caddy container | Public HTTPS unavailable | Low | Inspect logs; recreate Caddy |
| Control-plane container | UI/API unavailable | Low if PostgreSQL remains safe | Inspect logs; recreate exact image |
| PostgreSQL container/process | Readiness fails; app and worker lose durable state access | High if storage is damaged | Protect data; diagnose; restore if necessary |
| App Droplet | Entire public site and database unavailable | High because DB files are on that host | Recreate host; attach/restore data; update edge routing |
| Worker container | Site may load, but runs queue or fail | Low immediate data risk | Recreate exact worker image |
| Worker Droplet | Same as worker outage | Low immediate data risk | Recreate worker host and secrets |
| Cloudflare/DNS configuration | Domain may not reach origin | Low | Correct DNS/proxy configuration |
| GHCR access | New images cannot be pulled | Low while current containers run | Restore registry auth/access |
| Administrator laptop/key | Routine SSH access may be lost | Low if recovery access exists | Use controlled break-glass recovery |
| DigitalOcean account | Infrastructure control may be lost | Critical | Account recovery and independent backups |

### What degrades gracefully

The split architecture allows some partial failures:

- A worker outage does not have to erase learner data.
- Existing public pages may remain available while test execution is unavailable.
- A failed disposable execution container affects one Run Job rather than the app host.

But PostgreSQL is a shared dependency. The app and worker both depend on it, and it currently lives on the app Droplet. That makes database protection the highest operational priority.

### Redundancy is not the same as backup

- Redundancy keeps service running through some failures.
- Backups recover previous data after loss or corruption.

A database replica can faithfully replicate an accidental deletion. A backup can recover pre-deletion state. Mature systems often need both, but the beta should establish tested backups first.

---

## 8. Monitoring: detect what users care about

Monitoring has three parts:

```text
measure -> evaluate -> notify
```

A health endpoint without an external checker is only something you *could* inspect. An alert without a responsible recipient is only noise.

### The three existing health meanings

**Current:**

| Endpoint/check | Meaning |
|---|---|
| `/health/live` | The control-plane process is alive enough to answer HTTP |
| `/health/ready` | The control plane considers required dependencies ready |
| `/health/release` | The control plane and live workers agree on the expected source release and execution images |

These are deliberately different.

- Liveness asks whether a process should be restarted.
- Readiness asks whether traffic should be sent to it.
- Release readiness asks whether the distributed application is on a compatible release.

### Monitor from outside the infrastructure

**Next:** configure an independent uptime system to request at least:

- `https://makeitgreen.dev/health/ready`;
- `https://makeitgreen.dev/health/release`.

Why outside? A checker running only on the app Droplet cannot report that the Droplet itself is unreachable.

The alert should include:

- URL/check name;
- failure start time;
- HTTP status or connection error;
- region of the checker;
- link to the response procedure;
- current escalation contact.

### Host resource monitoring

**Next:** alert on:

- low free disk space and rapidly growing disk use;
- sustained high memory or out-of-memory kills;
- sustained high CPU/load;
- unexpected reboot or host unreachability;
- filesystem or I/O errors;
- time synchronization problems.

Disk is especially important because PostgreSQL data, Docker image layers, and container logs all consume the app host's finite disk.

### Container monitoring

Watch:

- container health state;
- restart count;
- unexpected exits and exit codes;
- memory and CPU consumption;
- image digest actually running;
- Docker daemon availability on the worker;
- orphaned challenge-run containers or Run Bundle directories.

Useful diagnostic commands include:

```bash
docker compose --env-file release.env --env-file runtime.env -f COMPOSE_FILE ps
docker compose --env-file release.env --env-file runtime.env -f COMPOSE_FILE logs --tail 200 SERVICE
docker inspect CONTAINER_NAME
docker stats --no-stream
docker system df
df -h
free -h
```

These commands inspect; they do not replace alerts.

### Application and queue monitoring

Eventually measure:

- request count and error rate;
- request latency percentiles;
- authentication failures;
- Run Jobs queued, running, failed, and completed;
- age of the oldest queued job;
- run duration;
- worker heartbeat age;
- admission-capacity rejections;
- abuse-control/rate-limit events;
- PostgreSQL connection and query health.

For this product, “oldest queued job age” is more useful than worker CPU alone. A worker can appear healthy while users wait too long.

### Start with symptoms, then causes

A good first dashboard separates:

**User symptoms:**

- public readiness failure;
- high API error rate;
- slow page/API responses;
- test jobs waiting too long;
- test jobs failing unexpectedly.

**Possible causes:**

- container unhealthy;
- worker heartbeat missing;
- PostgreSQL unavailable;
- host resource exhaustion;
- external dependency failure;
- wrong release mix.

Alert mainly on user symptoms and imminent resource exhaustion. Use cause metrics during diagnosis.

### Avoid alert fatigue

Every alert needs:

- an actionable condition;
- a clear owner;
- an urgency level;
- a runbook;
- a test proving notification delivery;
- periodic review.

If an alert regularly fires and requires no action, fix or remove it.

---

## 9. Logs and evidence

Logs answer “what happened?” Metrics answer “how much/how often?” Traces answer “where did time go across components?”

### Current limitation

Docker can show each container's recent logs, but local logs are tied to the host and its available disk. If the host is destroyed, its local incident evidence may disappear too.

### Next logging goals

- send important application and security events to off-host storage;
- include timestamps in UTC;
- include a request/job correlation identifier;
- distinguish app, worker, and execution-container events;
- retain logs for a defined period;
- redact authorization headers, cookies, tokens, passwords, and database URLs;
- alert on log delivery failure;
- cap or rotate local Docker logs so they cannot fill the disk.

### What never belongs in logs

- Clerk secret keys;
- bearer tokens or session cookies;
- GHCR tokens;
- SSH private keys;
- complete database URLs containing passwords;
- contents of secret files;
- unnecessary learner personal information.

### Preserve evidence during an incident

Before repeatedly restarting or deleting a failing container, collect:

```text
UTC time
symptom and affected user path
container status and restart counts
recent relevant logs
current image digests
release endpoint response
disk/memory/load state
recent deployment/configuration changes
```

Recovery comes first during severe impact, but avoid erasing the only evidence without recording it.

---

## 10. Secrets have a lifecycle

A secret is not complete when it has been generated. Its lifecycle is:

```text
create -> distribute -> store -> use -> rotate -> revoke -> destroy
```

### Current secret separation

**App host:**

- Clerk secret;
- API database URL;
- security-log HMAC key;
- PostgreSQL administrator password;
- PostgreSQL server certificate/key and CA certificate.

**Worker host:**

- worker database URL;
- the matching security-log HMAC key;
- PostgreSQL CA certificate.

This separation is valuable: the worker does not need the Clerk secret, and the app does not need the worker's database credential.

### Inventory without exposing values

Maintain a secure inventory of:

| Secret | Where used | Owner | Created | Rotation target | Revocation method |
|---|---|---|---|---|---|
| Clerk production secret | app | named person/team | date | policy | Clerk dashboard/API |
| GHCR access credential | each host | named person/team | date | policy | GitHub settings |
| API DB credential | app/PostgreSQL | named person/team | date | policy | PostgreSQL role change |
| Worker DB credential | worker/PostgreSQL | named person/team | date | policy | PostgreSQL role change |
| PostgreSQL TLS identity | app + worker trust | named person/team | date | before expiry | replace cert/key/CA as designed |
| Security-log HMAC key | app + worker | named person/team | date | policy | coordinated key transition |

Record metadata, not secret content.

### Rotation is a deployment

Changing a credential can break running services. A safe rotation normally follows:

1. understand every consumer;
2. create or stage the replacement;
3. update the server/provider side where necessary;
4. update consumers in a controlled order;
5. verify health and the real user path;
6. revoke the old credential;
7. remove staging copies;
8. record completion without recording the value.

Some secrets require overlapping old/new validity or application support for multiple keys. Do not rotate the shared HMAC key or certificate authority casually; first understand how previously signed records and all trust relationships are validated.

### If a token appears in chat, code, or logs

Treat it as compromised:

1. revoke it at its issuer;
2. create a replacement with the minimum required permissions;
3. update its intended consumers;
4. verify access;
5. search repositories, logs, shell history, artifacts, and screenshots for exposure;
6. document the incident without repeating the token.

Deleting the visible message is not equivalent to revocation.

### Registry credentials on these hosts

The `docker login` warning stated that credentials were stored in `/root/.docker/config.json` without a configured credential helper. Understand the consequence:

- root can read the credential material;
- a host compromise can expose registry access;
- the token should have only the scopes required to pull images;
- the token needs an owner, expiry/rotation policy, and revocation procedure.

Do not use a broad personal GitHub token indefinitely if a narrower machine/deployment credential is available.

---

## 11. Privileged access and the blast radius of mistakes

### `sudo -i`

`sudo -i` starts an interactive root shell. From then on, commands run with full system authority until `exit`.

The prompt is a safety signal:

```text
deployadmin@makeitgreen-app-1:~$     ordinary shell with sudo available
root@makeitgreen-app-1:~#           unrestricted root shell
```

Prefer individual `sudo COMMAND` invocations when practical. An interactive root shell is useful for a tightly scoped sequence involving protected files, but it increases the cost of a typo.

### Docker daemon access

The worker container controls the host Docker daemon through `/var/run/docker.sock`. The `deployadmin` user is also in the host's `docker` group. Docker's documentation warns that the group grants root-level privileges.

Why:

- Docker can mount host directories into containers;
- it can create containers with powerful namespace/capability settings;
- it controls processes and files owned by the daemon.

This is why the Docker socket exists only on the worker host and not on the public app host. It is also why a vulnerability in the worker deserves high priority.

### SSH access

Current protections include:

- public-key authentication;
- a non-root administrative account;
- a Cloud Firewall SSH rule restricted to one public source IP.

Next hardening questions include:

- Is direct root SSH disabled after `deployadmin` is proven?
- Is password SSH login disabled while keeping console recovery available?
- Are unused authorized keys removed?
- Is there a second controlled recovery administrator or break-glass path?
- What happens when the administrator's public IP changes?
- Are successful and failed logins reviewed?

Never change SSH policy while relying on a single untested session. Keep the working session open, validate syntax, reload safely, and prove a new connection in another terminal.

### Separate routine access from emergency access

- **Routine:** named administrator, SSH key, `sudo`, narrow firewall source.
- **Break glass:** protected recovery method used only when routine access fails.

The break-glass path should be documented and tested without weakening ordinary access.

---

## 12. Safe deployment and rollback

### A release is more than an image tag

The release contract connects:

```text
one Git source SHA
    + control-plane digest
    + worker digest
    + Python execution digest
    + Node execution digest
```

`release.env` contains exact digest references. Digest pinning ensures a future registry tag move cannot silently change the bytes started by Compose.

### Pre-deployment checklist

Before production mutation:

- CI is successful for the intended commit;
- vulnerability and smoke gates passed;
- all four application images come from the same release manifest;
- current working digests and configuration are recorded for rollback;
- new images are pre-pulled;
- Compose configuration validates;
- database migration compatibility is understood;
- backup freshness is inside the desired RPO;
- no unrelated incident is in progress;
- the operator knows which terminal is app, worker, and local;
- post-deployment checks and rollback conditions are written down.

### Deployment shape

The session used a controlled sequence:

1. update and validate the worker release references;
2. pull the worker and both execution images;
3. update and validate the app release reference;
4. pull the control-plane image;
5. recreate the worker;
6. recreate control plane and Caddy with health waiting;
7. verify public live, ready, and release endpoints;
8. verify an authenticated challenge and Run tests path;
9. keep rollback evidence until the observation window passes.

Pre-pulling separates “can the registry deliver this image?” from “should this healthy container be replaced now?”

### Rollback is not database restore

- **Application rollback:** run previously known-good image digests.
- **Configuration rollback:** restore previous reviewed settings.
- **Database restore:** replace damaged/current data with a backup.

These operations have very different consequences. Do not restore the database merely because a new frontend has a bug.

### Schema compatibility

An application rollback may fail if a deployment applied an incompatible database migration. Before applying a migration, answer:

- Can the old app run against the new schema?
- Is the migration additive or destructive?
- Does it lock large tables?
- How long should it take?
- What is the recovery procedure if it stops halfway?

Prefer expand/contract changes:

1. add backward-compatible schema;
2. deploy code that can use it;
3. migrate/backfill data;
4. remove old schema only after old code is no longer a rollback target.

### Rollback trigger examples

Rollback when a deployment causes:

- health checks that do not stabilize;
- a release mismatch that cannot be resolved promptly;
- authentication failure for valid invited users;
- editor assets that do not load;
- abnormal API error rate;
- Run Jobs that queue but do not complete;
- unexpected data writes or security boundary changes.

Do not improvise indefinitely while users are affected if a known-good rollback is available.

---

## 13. Incident response without panic

### The response loop

```text
Detect -> Declare -> Triage -> Stabilize -> Recover -> Verify -> Learn
```

### Step 1: state the symptom

Bad:

> Production is broken.

Better:

> Since 14:07 UTC, authenticated learners can open challenges, but Run Jobs remain queued for more than two minutes. Public readiness is 200; release readiness reports zero live workers.

The second description narrows the failing path.

### Step 2: declare impact and ownership

Record:

- incident start time in UTC;
- user-visible impact;
- severity;
- incident lead;
- current hypothesis;
- next update time.

For a solo beta operator, these notes can be a private incident document. The discipline still matters because memory becomes unreliable during stress.

### Step 3: draw the affected path

For public UI failure:

```text
browser -> DNS/Cloudflare -> firewall -> Caddy -> control plane -> PostgreSQL
```

For run failure:

```text
browser -> control plane -> PostgreSQL Run Job -> worker -> Docker -> execution image
```

Check the path from outside toward the deepest dependency. Do not restart every component simultaneously; that destroys evidence and makes the cause harder to identify.

### Step 4: inspect before mutating

Start with read-only evidence:

```bash
curl -i --max-time 15 https://makeitgreen.dev/health/live
curl -i --max-time 15 https://makeitgreen.dev/health/ready
curl -i --max-time 15 https://makeitgreen.dev/health/release
docker compose --env-file release.env --env-file runtime.env -f COMPOSE_FILE ps
docker compose --env-file release.env --env-file runtime.env -f COMPOSE_FILE logs --tail 200 SERVICE
df -h
free -h
```

Also check the latest deployment/configuration event and exact running image digests.

### Step 5: stabilize the service

Possible stabilizing actions depend on evidence:

- roll back the last application release;
- restart one failed stateless component;
- stop accepting new expensive work;
- restore missing worker capacity;
- increase disk safely or remove verified disposable data;
- block malicious traffic;
- restore the database into a controlled recovery path.

Choose the smallest action that reduces impact without expanding the failure.

### Step 6: verify recovery at multiple layers

Do not stop at “container is running.” Verify:

1. process/container state;
2. dependency readiness;
3. distributed release agreement;
4. public HTTPS;
5. authentication;
6. challenge editor content;
7. one real Run tests flow;
8. monitoring recovery.

### Step 7: learn afterward

A useful review answers:

- What happened?
- When did it begin and end?
- What was the user impact?
- Why did the system allow it?
- Why did detection take as long as it did?
- What helped recovery?
- What made recovery harder?
- Which specific corrective actions will prevent or reduce recurrence?

Avoid “be more careful” as the only action. Prefer guardrails, validation, tests, automation, and clearer ownership.

---

## 14. Disaster recovery scenarios to rehearse

Disaster recovery is easier when decomposed into scenarios.

### Scenario A: worker host is permanently lost

Expected effect:

- public app may still load;
- new Run Jobs cannot complete until worker capacity returns;
- durable learner state remains on the app/PostgreSQL host.

Recovery outline:

1. create a replacement worker Droplet in the correct region/VPC;
2. apply the restricted worker firewall/tag policy;
3. create and verify `deployadmin` access;
4. install the pinned Docker tooling;
5. create `/srv/makeitgreen` directories with numeric ownership;
6. install worker Compose/runtime/release files;
7. provision only worker-required secrets;
8. authenticate narrowly to GHCR;
9. pull the exact worker and execution images;
10. start the worker;
11. verify container health and `/health/release`;
12. run one authenticated challenge.

This scenario should become mostly infrastructure/configuration automation.

### Scenario B: app host fails but database storage is recoverable

Recovery must account for:

- Caddy/public routing;
- control-plane service;
- PostgreSQL data and correct ownership;
- VPC private address/certificate SAN relationship;
- firewall targets/tags;
- secrets;
- Cloudflare origin address;
- worker database URL.

Changing the app's private IP may invalidate the PostgreSQL server certificate or worker URL. This is one reason stable infrastructure definitions and a rehearsed certificate process matter.

### Scenario C: PostgreSQL data is corrupted or deleted

Recovery outline:

1. stop or isolate writers;
2. preserve evidence and current storage if possible;
3. identify the incident time and required recovery point;
4. provision a clean compatible PostgreSQL instance;
5. restore the selected dump or PITR chain;
6. recreate/rotate runtime credentials as designed;
7. verify schema, data, and grants;
8. connect an isolated control plane and perform smoke checks;
9. cut traffic/workers over deliberately;
10. verify user journeys and monitor closely.

Never repeatedly experiment on the only remaining copy of damaged data.

### Scenario D: credentials are exposed

Recovery is revocation, not merely file deletion:

1. identify the credential and its scope;
2. revoke it at the issuer/database;
3. replace it with minimum permissions;
4. update intended consumers;
5. search for unauthorized use and additional exposure;
6. verify service health;
7. document timeline and prevention work.

### Scenario E: bad application release

Recovery normally uses the prior release manifest/digests, not a database restore. Preserve the new failure logs, restore compatible images in a controlled order, verify `/health/release`, then retest the user journey.

---

## 15. Capacity and performance

Availability can fail because the system is overloaded even when every component is technically alive.

### Current admission and worker limits

The deployment currently configures concepts such as:

- global active-run cap;
- per-user active-run cap;
- requests and mutations per minute;
- runs per minute;
- worker concurrency;
- per-run memory;
- execution CPU, process, file, temporary-storage, and timeout limits.

These protect the beta from one user or burst consuming unlimited resources.

### Queueing is expected; unbounded queueing is not

If arrival rate exceeds execution rate:

```text
queued jobs increase -> wait time increases -> leases/timeouts/failures may follow
```

Measure:

- jobs arriving per minute;
- jobs completing per minute;
- queue length;
- oldest queued age;
- run-duration distribution;
- failure reason;
- worker memory pressure and OOM events.

### Scale only after measuring

Possible future scaling choices:

- raise worker concurrency if measured memory/CPU headroom permits;
- use a larger worker Droplet;
- add more worker Droplets using the durable claim protocol;
- tune per-run limits;
- reduce expensive challenge workloads;
- reject excess work clearly instead of allowing collapse.

Every increase in concurrency multiplies possible memory use. Capacity tests should decide the value, not optimism.

---

## 16. Automation roadmap

Automation should encode a procedure that is already understood and tested.

### Priority 1: backups and restore evidence

Build:

- scheduled PostgreSQL-aware backups;
- encrypted off-host upload;
- retention policy;
- backup-age and failure alert;
- automated checksum verification;
- recurring isolated restore drill.

### Priority 2: external monitoring

Build:

- public ready/release checks;
- notification routing;
- disk/memory/host alerts;
- worker-heartbeat and queue-age alerts;
- tested alert delivery;
- links from alerts to this runbook.

### Priority 3: infrastructure as code

Define in version control:

- VPC;
- Droplets and sizes/images;
- firewall rules and tags;
- monitoring policies;
- backup policy;
- reserved/static addressing where chosen;
- DNS where provider integration permits.

Terraform's DigitalOcean provider can describe Droplets, VPC association, firewall rules, and backup policy. Review every plan before applying it; infrastructure-as-code can reproduce mistakes as efficiently as correct configuration.

### Priority 4: configuration management

Automate repeatable host state:

- OS packages and Docker repository;
- users and SSH policy;
- `/srv/makeitgreen` directories and ownership;
- Compose/config installation;
- service startup and verification;
- log rotation;
- security updates and reboot policy.

Keep secret values in a proper secret-delivery channel, not inside the automation repository.

### Priority 5: deployment orchestration

Turn the manual release sequence into a tool that:

- accepts one verified release manifest;
- backs up current release metadata;
- validates both host configurations;
- pre-pulls all images;
- applies hosts in the intended order;
- waits for health;
- verifies `/health/release` and a smoke path;
- records evidence;
- stops and offers a safe rollback when verification fails.

Automation must fail closed. Silence should not mean success; every stage should produce explicit evidence.

---

## 17. A safe routine operations calendar

### Every deployment

- confirm the intended commit and all image digests;
- confirm recent backup success;
- pre-pull and validate;
- keep rollback references;
- verify ready/release endpoints;
- test authentication, editor loading, and one run;
- observe logs/metrics during a short post-deployment window.

### Daily automated checks

- public ready/release availability;
- backup completion and age;
- disk/memory/CPU thresholds;
- PostgreSQL/container health;
- worker heartbeat and oldest queued-job age;
- certificate expiry horizon;
- unexpected container restart counts.

### Weekly human review

- review failed/slow runs and abnormal authentication/rate-limit events;
- review host and Docker disk usage;
- review pending OS and Docker security updates;
- ensure monitoring notifications still reach an owner;
- confirm backup artifacts exist outside the app host.

### Monthly

- perform and record an isolated restore drill;
- review access keys, users, and token scopes;
- review secret/certificate rotation dates;
- test one incident scenario;
- review alert noise and missing coverage;
- review capacity trends and costs.

### Quarterly or after major architecture changes

- recreate a host from documentation/automation;
- review RPO/RTO with product needs;
- review firewall, VPC, DNS, and Cloudflare configuration;
- rehearse a full app-host recovery;
- update diagrams and runbooks.

---

## 18. Beginner-safe command habits

### Identify context before every privileged command

Run:

```bash
hostname
whoami
pwd
```

Then describe the target in plain English:

> I am root on the worker host in `/srv/makeitgreen`, and this command will recreate only the execution-worker container.

If you cannot complete that sentence, stop and inspect.

### Separate read-only checks from mutations

Read-only examples:

```bash
docker compose ... ps
docker compose ... logs --tail 200 SERVICE
docker inspect CONTAINER
stat FILE
df -h
free -h
curl -i URL
```

Mutation examples:

```bash
docker compose ... up -d --force-recreate
chmod
chown
sed -i
systemctl restart
apt-get upgrade
rm
```

Inspect first, state the expected effect, mutate one thing, and verify.

### Treat line wrapping as dangerous

Several session errors occurred because the shell interpreted a visually wrapped command as two commands. Before pasting:

- prefer one short command per line;
- do not place a redirection target on a separate line accidentally;
- use a reviewed script for multi-step repeated operations;
- understand that a backslash must be the final character on the line;
- avoid pasting prompts or output back into the shell.

### Understand redirection privilege

In:

```bash
sudo SOME_COMMAND > /root/output
```

`sudo` applies to `SOME_COMMAND`, but the current shell performs `> /root/output`. The redirection may still fail for an unprivileged shell. This is one reason protected file creation often uses a root shell, `sudo tee`, or a carefully reviewed script.

### Never test destructive commands by guessing

Resolve the exact path first with `pwd`, `stat`, `find`, or `ls`. Avoid broad recursive deletion, globs, unresolved variables, and commands copied from an unrelated host.

---

## 19. First 30 days: a learning and implementation plan

### Week 1: data and recovery fundamentals

Read:

- Sections 1–6 of this guide;
- PostgreSQL backup, SQL dump, and `pg_restore` documentation.

Practice outside production:

- create a small PostgreSQL database;
- make a custom-format dump;
- delete the lab database;
- restore into a fresh database;
- verify rows and permissions;
- record RPO and RTO in your own words.

Deliverable:

- a written MakeItGreen backup design with storage, encryption, frequency, retention, ownership, and restore test.

### Week 2: visibility

Read:

- Sections 7–9;
- SRE monitoring material;
- DigitalOcean Monitoring documentation;
- Docker logging documentation.

Practice:

- build a dashboard/checklist for health, disk, memory, containers, worker heartbeat, and queue age;
- trigger a test alert and prove the notification arrives;
- stop a lab service and describe the symptom before examining the cause.

Deliverable:

- external ready/release monitoring plus an alert contact and response link.

### Week 3: access, secrets, and releases

Read:

- Sections 10–12;
- OWASP secret lifecycle guidance;
- Docker daemon security guidance.

Practice:

- make a non-secret credential inventory template;
- simulate rotating a lab database user's password with minimal downtime;
- trace a commit to its image digests and back;
- perform a lab application rollback without touching database data.

Deliverable:

- secret inventory and rotation schedule, plus a deployment/rollback checklist.

### Week 4: incidents and automation

Read:

- Sections 13–18;
- SRE incident-management and postmortem material;
- DigitalOcean Terraform examples.

Practice:

- simulate a dead worker;
- diagnose using the run path;
- restore service;
- write a short incident timeline and corrective actions;
- describe one Droplet/firewall/VPC in Terraform in a non-production project.

Deliverable:

- one rehearsed incident runbook and a prioritized infrastructure-as-code plan.

---

## 20. Staff-engineer decision questions

Before approving an operational change, ask:

### User impact

- What user capability could this interrupt?
- How will we know if it is interrupted?
- What is the acceptable interruption window?

### Data

- Does this touch the only copy of persistent data?
- What is the newest verified recovery point?
- Has this exact restore path been tested?

### Security

- Does this expand a network path, identity permission, or host mount?
- Does a secret appear in arguments, output, logs, or shell history?
- What is the blast radius if this credential/component is compromised?

### Change safety

- What exact state exists before the change?
- What exact state should exist after it?
- Can configuration be validated without mutation?
- What is the smallest change that achieves the outcome?
- What automatically or manually rolls it back?

### Evidence

- Which command or user journey proves success?
- Which evidence proves the exact deployed version?
- How long should we observe before declaring completion?

### Ownership

- Who receives alerts?
- Who can revoke credentials?
- Who can restore backups?
- Could another person follow the runbook under pressure?

These questions are not bureaucracy. They expose hidden dependencies before production exposes them for you.

---

## 21. Self-test

Try answering without looking below.

1. Why is a successful `docker compose ps` not proof that users can use the product?
2. What is the difference between RPO and RTO?
3. Why is a backup file not enough to claim recoverability?
4. Which MakeItGreen data is irreplaceable?
5. Why should PostgreSQL backups leave the app Droplet?
6. Why is a Droplet snapshot not the same as a tested PostgreSQL restore?
7. What is the difference between redundancy and backup?
8. What failure occurs if the worker disappears but PostgreSQL and the app stay healthy?
9. Why should health monitoring run outside the app Droplet?
10. What does `/health/release` prove beyond liveness?
11. Why is queue age a better user signal than worker CPU alone?
12. Why can local container logs be insufficient during host loss?
13. Why is Docker group membership effectively administrative access?
14. What should you do if a real token appears in chat or logs?
15. Why is secret rotation itself a deployment?
16. What is the difference between application rollback and database restore?
17. Why can database migrations make rollback harder?
18. What evidence should be collected before repeatedly restarting a component?
19. Why should infrastructure automation be reviewed even though it improves repeatability?
20. What are the first three operational priorities for this beta?

<details>
<summary>Answer key</summary>

1. It proves container state, not public routing, authentication, browser behavior, distributed worker compatibility, or the real user journey.
2. RPO is acceptable data-loss time; RTO is acceptable recovery duration.
3. Only a successful restore and application verification prove the artifact is usable.
4. Primarily PostgreSQL learner/application state, plus separately protected identity/secret material needed for recovery.
5. A host/disk/account failure must not destroy both live data and its only recovery copy.
6. It is a whole-host recovery mechanism with different portability, schedule, consistency, and testing properties.
7. Redundancy continues service; backup restores earlier data.
8. Pages may work, but Run Jobs will wait or fail because nothing claims and executes them.
9. An internal checker can disappear with the component it is supposed to report on.
10. The control plane sees live workers using a compatible source release and execution image set.
11. CPU may look normal while jobs are stuck; queue age directly represents learner waiting.
12. Logs can disappear with the destroyed host and may consume the same failing disk.
13. Docker can start powerful containers and mount host files, enabling host-level control.
14. Revoke it, replace it with minimum scope, update consumers, investigate exposure, and verify service.
15. Multiple consumers and providers must transition in a safe order without breaking authentication.
16. App rollback changes executable images; database restore replaces current state with an earlier recovery point.
17. Old code may not understand a newly changed schema, especially after destructive changes.
18. UTC time, symptoms, status/restarts, relevant logs, running digests, health responses, resources, and recent changes.
19. Automation can apply a mistaken definition consistently and at large scope.
20. Tested off-host database backups, external monitoring/alerts, and a repeatable deployment/rollback runbook.

</details>

---

## 22. Repository and documentation map

### MakeItGreen sources

| Concern | File |
|---|---|
| How the production deployment was built | [`PRODUCTION_DEPLOYMENT_SESSION_GUIDE.md`](PRODUCTION_DEPLOYMENT_SESSION_GUIDE.md) |
| Deployment topology and manual startup | [`../deploy/README.md`](../deploy/README.md) |
| App persistence, health, secrets, networks | [`../deploy/app/compose.app.yaml`](../deploy/app/compose.app.yaml) |
| Worker privilege, health, and limits | [`../deploy/worker/compose.worker.yaml`](../deploy/worker/compose.worker.yaml) |
| Deployment validation | [`../scripts/validate_deployment.py`](../scripts/validate_deployment.py) |
| Release readiness wait helper | [`../scripts/wait_for_release.sh`](../scripts/wait_for_release.sh) |
| Image promotion logic | [`../scripts/promote_images.sh`](../scripts/promote_images.sh) |
| Image-tag rollback logic | [`../scripts/restore_images.sh`](../scripts/restore_images.sh) |
| Database migration contract | [`../backend/migrations/README.md`](../backend/migrations/README.md) |
| Durable Run Job coordination | [`../backend/run_coordination.py`](../backend/run_coordination.py) |
| Execution isolation policy | [`../backend/runner.py`](../backend/runner.py) |

### Primary learning references

- [PostgreSQL 17 backup and restore](https://www.postgresql.org/docs/17/backup.html)
- [DigitalOcean backups](https://docs.digitalocean.com/products/backups/)
- [DigitalOcean Monitoring](https://docs.digitalocean.com/products/monitoring/)
- [Docker storage](https://docs.docker.com/engine/storage/)
- [Docker logging](https://docs.docker.com/engine/logging/)
- [Docker security](https://docs.docker.com/engine/security/)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Google SRE book](https://sre.google/sre-book/table-of-contents/)

---

## 23. Final mental model

Operating MakeItGreen means repeatedly protecting four flows:

```text
User flow
  browser -> edge -> app -> database -> worker -> execution result

Data flow
  live PostgreSQL -> verified backup -> off-host retention -> tested restore

Change flow
  commit -> CI -> immutable digests -> staged deployment -> verification -> rollback

Incident flow
  alert -> evidence -> narrow diagnosis -> stabilization -> recovery -> learning
```

The practical priorities are simple even though the field is broad:

1. Know which data cannot be recreated.
2. Keep verified recovery copies outside the live host.
3. Detect user-impacting failures from outside the system.
4. Minimize and record privileged access.
5. Make changes from immutable, reviewable inputs.
6. Preserve a known-good return path.
7. Practice recovery before an emergency.

Production engineering is not the absence of failure. It is the ability to detect failure quickly, limit its blast radius, restore the service and its data predictably, and improve the system afterward.
