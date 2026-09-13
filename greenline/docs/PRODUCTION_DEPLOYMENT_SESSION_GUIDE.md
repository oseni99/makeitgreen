# MakeItGreen production deployment: what we built, why it works, and how to reason about it

This document explains the production setup completed on September 12, 2026. It is written for a developer who can build application code but is new to production infrastructure.

After this guide, continue with the companion [production operations and recovery guide](PRODUCTION_OPERATIONS_AND_RECOVERY_GUIDE.md), which covers backups, restore drills, monitoring, secrets, failures, incident response, and repeatable operations.

It has four goals:

1. Give you the mental model that the commands alone did not provide.
2. Reconstruct what we did, in order, and explain why each step existed.
3. Show how the parts work together when a learner opens a challenge and runs tests.
4. Give you a reading path and an operating checklist so the system stops feeling mysterious.

This is not a password or secret inventory. Never add real credentials, private keys, database passwords, Clerk secret keys, or GitHub tokens to this document or to Git.

The IP addresses below are documentation-only examples. Public examples use
the reserved `192.0.2.0/24` and `198.51.100.0/24` ranges, and private examples
use `10.20.0.0/20`. Discover the intended environment's real addresses instead
of copying these examples into commands.

---

## 1. The result in one picture

The system has two DigitalOcean virtual machines, called Droplets:

```text
Learner's browser
        |
        | HTTPS request for makeitgreen.dev
        v
Cloudflare DNS + HTTP proxy
        |
        | HTTPS to the app Droplet's public IP
        v
DigitalOcean Cloud Firewall
        |
        | ports 80/443 only
        v
App Droplet: makeitgreen-app-1
public:  192.0.2.10
private: 10.20.0.2
        |
        +-- Caddy container
        |      terminates HTTPS and adds security headers
        |      reverse-proxies requests to control-plane:8000
        |
        +-- Control Plane container
        |      serves the React application and API
        |      authenticates users with Clerk
        |      stores durable state and queues jobs in PostgreSQL
        |
        +-- PostgreSQL container
               internal app access: Docker database network
               worker access: 10.20.0.2:5432 over the private VPC

                         DigitalOcean private VPC
                         10.20.0.0/20
                                  |
                                  | TLS PostgreSQL connection
                                  v
Worker Droplet: makeitgreen-worker-1
public:  198.51.100.20
private: 10.20.0.3
        |
        +-- Execution Worker container
        |      polls PostgreSQL for queued run jobs
        |      has controlled access to the host Docker daemon
        |
        +-- Disposable Python/Node execution containers
               receive one run bundle
               run the learner's tests with resource limits
               disappear after the run
```

The most important design decision is the split between the two hosts:

- The **app host** accepts public web traffic but does not mount the Docker daemon socket.
- The **worker host** can create code-execution containers but exposes no public application port.
- PostgreSQL is reachable by the worker only through the private VPC, TLS, database authentication, and firewall rules.

This is a trust boundary. Untrusted learner code is kept away from the public web server and the application host's Docker daemon.

### What happens when a learner clicks **Run tests**

This is the most useful end-to-end story to keep in your head:

```text
Browser                  App host / control plane       PostgreSQL              Worker host
   |                               |                        |                         |
   | save every edited file       |                        |                         |
   |------------------------------>| write durable state   |                         |
   |                               |----------------------->|                         |
   |                               |                        |                         |
   | POST /api/challenges/:slug/runs                        |                         |
   |------------------------------>| authenticate + admit  |                         |
   |                               | enqueue job + revision |                         |
   |                               |----------------------->|                         |
   |<------------------------------| 202 + job_id           |                         |
   |                               |                        |                         |
   | GET /api/run-jobs/:id repeatedly                       | worker claims job       |
   |------------------------------>|----------------------->|<------------------------|
   |                               |                        | return workspace snapshot
   |                               |                        |------------------------->|
   |                               |                        |                         |
   |                               |                        |      create one fresh Docker
   |                               |                        |      execution container
   |                               |                        |      and run the tests
   |                               |                        |                         |
   |                               |                        |<-- output + heartbeat ---|
   |<-- incremental output --------|<-----------------------|                         |
   |                               |                        |<-- final result ---------|
   |<-- completed result ----------|<-----------------------|                         |
   |                               |                        |      remove container + bundle
```

In more detail:

1. The React workspace calls `saveAll()` before submitting the run. A test run therefore targets saved, server-side state—not an unrecorded editor buffer.
2. The frontend sends `POST /api/challenges/{slug}/runs` with the Clerk bearer token. The control plane requires a verified learner identity in Hosted Mode.
3. The control plane performs admission control, snapshots the workspace revision, creates a durable `queued` row in PostgreSQL, and returns a job ID with HTTP `202 Accepted`.
4. The browser polls `GET /api/run-jobs/{job_id}`. It asks only for output after its last offset and updates the Results drawer while the job runs.
5. The worker polls PostgreSQL and claims one eligible job. `FOR UPDATE ... SKIP LOCKED` prevents two workers from claiming the same available row. A claim token, fence, lease, and heartbeat prevent a stale worker from later overwriting a newer result.
6. Before executing, the worker reloads the workspace and verifies that its revision still matches the revision captured when the job was enqueued. If the code changed in between, the stale run is rejected instead of testing ambiguous input.
7. The worker materializes a temporary **Run Bundle** under `/srv/makeitgreen/run-bundles` and asks the host Docker daemon to create a fresh Python or Node container.
8. That disposable container is deliberately constrained:

   - `--network none`: learner code has no network interface;
   - `--read-only`: the image's root filesystem cannot be changed;
   - `--cap-drop ALL`: Linux capabilities are removed;
   - `--security-opt no-new-privileges`: processes cannot gain extra privileges;
   - `--user 65534:65534`: learner execution is not root (this is distinct from the long-running worker container's `65532:65532` identity);
   - CPU, memory, process-count, open-file, and execution-time limits are set;
   - only controlled temporary filesystems are writable;
   - the Run Bundle is mounted read-only and copied into an isolated workspace.

9. Test output is appended to the PostgreSQL job record while the worker renews its claim. The browser receives it through polling; the worker does **not** need a public HTTP port.
10. On completion, PostgreSQL records the test counts, exit code, output tail, learner progress, and restorable workspace snapshot. The worker removes the disposable container and temporary Run Bundle in a `finally` cleanup path.

This explains the architecture. The control plane owns public HTTP, identity, durable state, and job admission. The worker owns dangerous execution authority. PostgreSQL is the coordination bridge between them.

---

## 2. Read this before touching production again

Do not try to learn every product at once. Read in this order.

### Stage 1: terminal and Linux foundations

Learn these concepts first:

- current working directory, absolute path, and relative path;
- files, directories, ownership, users, groups, and permission modes;
- standard input, standard output, pipes, redirection, and shell quoting;
- processes, services, ports, and logs;
- the difference between a local terminal and an SSH session.

Start with:

- [Ubuntu: Welcome to the terminal](https://ubuntu.com/server/docs/tutorial/welcome-to-the-terminal/)
- [Linux Journey](https://linuxjourney.com/)
- On a Linux host, read `man chmod`, `man chown`, `man sudo`, `man systemctl`, and `man journalctl`.

Do not move on until you can explain the difference between these prompts:

```text
oluwatosin@MacBook ~ %
deployadmin@makeitgreen-app-1:~$
root@makeitgreen-worker-1:/srv/makeitgreen#
```

They represent three different machines/users/privilege levels.

### Stage 2: networking foundations

Learn:

- IPv4 addresses and CIDR notation;
- public versus private IP addresses;
- ports and TCP connections;
- DNS names versus IP addresses;
- inbound versus outbound traffic;
- firewalls and stateful connection tracking;
- HTTP versus HTTPS and what TLS certificates prove.

Start with:

- [Cloudflare: What is DNS?](https://www.cloudflare.com/learning/dns/what-is-dns/)
- [DigitalOcean VPC quickstart](https://docs.digitalocean.com/products/networking/vpc/getting-started/quickstart/)
- [DigitalOcean: Configure firewall rules](https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/)
- [MDN: HTTP overview](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview)

### Stage 3: SSH and server administration

Learn:

- SSH client versus the `sshd` server;
- private key versus public key;
- host keys versus user keys;
- why `root` is special;
- what `sudo` does;
- why you keep an existing SSH session open while testing a new SSH configuration.

Start with:

- [Ubuntu OpenSSH server guide](https://ubuntu.com/server/docs/how-to/security/openssh-server/)
- [Ubuntu user management](https://ubuntu.com/server/docs/how-to/security/user-management/)

### Stage 4: Docker and Compose

Learn these in order:

1. image;
2. container;
3. registry;
4. Dockerfile;
5. volume/bind mount;
6. bridge network;
7. Docker Compose service;
8. health check;
9. digest pinning;
10. Docker daemon and `/var/run/docker.sock`.

Start with:

- [Docker: What is an image?](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-an-image/)
- [Docker: What is a container?](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/)
- [Docker Compose introduction](https://docs.docker.com/compose/)
- [Docker build best practices](https://docs.docker.com/build/building/best-practices/)
- [Docker Linux post-installation](https://docs.docker.com/engine/install/linux-postinstall/)

Important security fact: membership in the `docker` group is effectively root-level access. A user who can control the Docker daemon can normally mount host files or start a privileged container. Treat `deployadmin` as an administrator, not as a low-privilege application user.

### Stage 5: web edge and browser security

Learn:

- DNS `A` records;
- Cloudflare proxied versus DNS-only records;
- reverse proxies;
- TLS termination;
- Content Security Policy (CSP);
- browser Web Workers;
- browser caching and hashed asset filenames.

Start with:

- [Cloudflare: Manage DNS records](https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/)
- [Cloudflare: Proxy status](https://developers.cloudflare.com/dns/proxy-status/)
- [Caddy reverse proxy quick-start](https://caddyserver.com/docs/quick-starts/reverse-proxy)
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [MDN: Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy)
- [MDN: `worker-src`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/worker-src)

### Stage 6: PostgreSQL operations and access control

Learn:

- database cluster, database, schema, table, and role;
- data-definition language (DDL) versus runtime data access;
- migrations;
- least-privilege roles;
- `pg_hba.conf`;
- SCRAM password authentication;
- TLS certificate authorities, server certificates, and hostname verification.

Start with:

- [PostgreSQL 17: Client authentication](https://www.postgresql.org/docs/17/client-authentication.html)
- [PostgreSQL 17: `pg_hba.conf`](https://www.postgresql.org/docs/17/auth-pg-hba-conf.html)
- [PostgreSQL 17: SSL support](https://www.postgresql.org/docs/17/ssl-tcp.html)
- The repository's [migration guide](../backend/migrations/README.md)

### Stage 7: CI/CD and software supply chain

Learn:

- Git commits and commit SHAs;
- CI gates;
- container registries;
- tags versus immutable image digests;
- vulnerability scans;
- SBOMs;
- provenance and attestations;
- staged deployment and rollback.

Start with:

- [GitHub Actions](https://docs.github.com/en/actions)
- [GitHub: Publishing Docker images](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker: Pin base image versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)

### Stage 8: Monaco Editor and Vite

Only study this after the browser-security section:

- [Monaco React: use `monaco-editor` as an npm package](https://github.com/suren-atoyan/monaco-react#use-monaco-editor-as-an-npm-package)
- [Vite Web Workers](https://vite.dev/guide/features.html#web-workers)
- [Monaco Editor repository](https://github.com/microsoft/monaco-editor)

### A practical seven-day study plan

Reading alone will not make this system intuitive. Use a throwaway local VM or local Docker project for the exercises; do not experiment directly on production.

**Day 1 — shell, machines, and identity**

- Read Stage 1.
- Practice `pwd`, `whoami`, `hostname`, `id`, `ls -la`, `stat`, `chmod`, and `chown` in a temporary directory.
- Open one local terminal and one SSH session. Say aloud which machine and which user owns each prompt.
- Goal: predict whether a command affects your Mac, the app server, or the worker server before pressing Enter.

**Day 2 — packets, addresses, DNS, and ports**

- Read Stage 2.
- Draw the route from `makeitgreen.dev` to Cloudflare to the app public IP to Caddy.
- Use `dig makeitgreen.dev`, `curl -v https://makeitgreen.dev/health/live`, `ip -4 -brief address` on a server, and `ss -lnt` on a lab host.
- Goal: explain why `10.20.0.2` works between Droplets but is not an address a learner can browse to.

**Day 3 — SSH and least privilege**

- Read Stage 3.
- In a disposable VM, create a non-root user, add an SSH public key, test login in a second terminal, then test `sudo whoami`.
- Compare the server host key with your user's authorized key. They solve different authentication problems.
- Goal: explain why the original root session stayed open until `deployadmin` login and `sudo` were proven.

**Day 4 — Docker basics**

- Read the image, container, volume, and network material in Stage 4.
- Run a simple container, inspect it, view its logs, stop it, remove it, and prove the image remains.
- Start two Compose services on a private bridge network. Publish only one service's port.
- Goal: explain why `8000/tcp` in `docker compose ps` is not automatically a public host port.

**Day 5 — Compose, persistence, and isolation**

- Add a health check and a bind mount to the lab Compose project.
- Run a container with `--network none`, `--read-only`, `--cap-drop ALL`, a non-root `--user`, and a memory limit. Observe which operations fail.
- Delete and recreate a stateless container while preserving data in a mounted directory.
- Goal: distinguish replaceable containers from persistent host data.

**Day 6 — PostgreSQL, TLS, and secrets**

- Read Stage 6.
- Create an owner role and a restricted runtime role in a local PostgreSQL instance. Test an allowed query and a deliberately forbidden operation.
- Inspect a test certificate with `openssl x509`; learn why a CA file and SAN are checked by `verify-full`.
- Practice creating a secret file with `umask 077`, then verify its numeric owner and mode with `stat`.
- Goal: explain why a network path, TLS certificate, database role, and password are separate layers—not substitutes for one another.

**Day 7 — trace one release and one request**

- Read Stages 7 and 8, then Sections 7 through 10 of this guide.
- Pick one Git commit. Follow it through CI, image build, registry digest, `release.env`, Compose recreation, and `/health/release`.
- Then trace one **Run tests** click using the lifecycle above.
- Goal: answer two questions independently: “Which code is deployed?” and “What happens to this request?”

At the end of the week, repeat the questions in Section 17 without looking at the answer key. Anything you cannot explain becomes the next reading or lab topic.

---

## 3. Core vocabulary in plain English

### Host, image, container, and service

- A **host** is the actual virtual machine. Our hosts are the two DigitalOcean Droplets.
- An **image** is an immutable application package: code, runtime, dependencies, and metadata.
- A **container** is a running process created from an image.
- A **Compose service** is the desired configuration for one kind of container: its image, environment, secrets, networks, mounts, health check, and restart policy.

An image is like a sealed application template. A container is one running instance of that template. Compose is the document describing which instances should exist and how they connect.

### Public IP, private IP, and Docker-network IP

Each app host address had a different purpose:

```text
192.0.2.10   public app IP; reachable from the internet when firewalls allow it
10.20.0.2        app's DigitalOcean VPC IP; reachable only inside the VPC
172.30.0.x        app's Docker proxy bridge; local to the app host
172.31.0.x        app's Docker database bridge; local to the app host
127.0.0.1         loopback; means "this same machine/container"
```

The worker similarly had:

```text
198.51.100.20    public worker IP, used for tightly restricted SSH
10.20.0.3        worker's DigitalOcean VPC IP
172.17.0.1        host-side default Docker bridge address
```

Private addresses do not automatically mean "secure." They reduce exposure, but you still use a firewall, TLS, authentication, and least-privilege database roles.

### CIDR and `/32`

`162.216.145.120/32` means exactly one IPv4 address. The `/32` says all 32 address bits must match.

By comparison:

```text
0.0.0.0/0        every IPv4 address
10.20.0.0/20    a private network containing many addresses
162.216.145.120/32 exactly one address
```

### Port

An IP identifies a machine/interface. A port identifies a listening network service on that machine.

```text
22     SSH
80     HTTP
443    HTTPS (and HTTP/3 uses UDP 443)
5432   PostgreSQL
8000   MakeItGreen control-plane process inside its container
2375   conventional unencrypted Docker API port; intentionally not exposed
2376   conventional TLS Docker API port; intentionally not exposed
```

### DNS and proxying

DNS answers, "Which address handles `makeitgreen.dev`?"

The Cloudflare `A` record pointed the root name (`@`) toward the app Droplet's public IP. With the orange-cloud proxy enabled, visitors normally receive Cloudflare addresses, and Cloudflare forwards their HTTP/HTTPS requests to the app origin. Cloudflare is in the web request path; it is not in the SSH or private PostgreSQL path.

### TLS and certificate verification

Encryption alone is insufficient if the client cannot verify who it reached. `sslmode=verify-full` requires:

1. an encrypted connection;
2. a certificate signed by the trusted CA;
3. a hostname/IP match against the certificate's Subject Alternative Names.

The PostgreSQL server certificate was verified for:

```text
DNS: postgres
IP: 10.20.0.2
```

That supports the two names used by clients: the app's internal Docker hostname and the worker's VPC destination.

### Hash, digest, and commit SHA

These are identifiers with different jobs:

- A **Git commit SHA** identifies a source-code snapshot.
- A container **image digest** such as `sha256:...` identifies exact image bytes/manifest.
- A tag such as `latest`, `main`, or `production` is a movable label.

We deployed digests, not mutable tags. That lets us say exactly which bytes are running and roll back to known bytes.

---

## 4. What `api.ipify.org` was doing

This was one of the most confusing moments, so it deserves its own section.

Your laptop likely has a private address on your home or school network, such as `192.168.x.x` or `10.x.x.x`. Your router performs Network Address Translation (NAT). Websites do not see the laptop's private address; they see the router/ISP's public egress address.

`https://api.ipify.org` is a simple service that replies with the public IP address from which it received your request. We used it to learn what source IP the DigitalOcean firewall would see when your laptop initiated SSH.

It did **not**:

- create another firewall;
- create a permanent connection;
- reveal a server's private VPC address;
- route future SSH traffic;
- become part of MakeItGreen.

It was a one-time "what public address do I appear to come from?" check.

We placed that result into the SSH inbound rule as `162.216.145.120/32`, meaning only that one public IPv4 address could initiate SSH connections.

If your ISP changes your public IP, SSH will time out until you update the firewall rule. Re-run the public-IP check from the network you are currently using. Do not replace `/32` with `0.0.0.0/0` merely for convenience.

---

## 5. The two DigitalOcean firewalls

They were two separate firewall objects because the hosts have different responsibilities.

### App firewall

Conceptually, its inbound rules were:

| Port | Allowed source | Reason |
|---|---|---|
| TCP 22 | your public IP `/32` | administration over SSH |
| TCP 80 | all IPv4/IPv6 | HTTP redirect and certificate operations |
| TCP 443 | all IPv4/IPv6 | public HTTPS application traffic |
| TCP 5432 | worker Droplet/tag only | worker-to-PostgreSQL traffic |

Its outbound rules allowed ICMP, TCP, and UDP so the host could resolve DNS, download packages/images, obtain certificates, reach Clerk, and perform other expected outbound work.

### Worker firewall

Conceptually, its inbound rules were:

| Port | Allowed source | Reason |
|---|---|---|
| TCP 22 | your public IP `/32` | administration over SSH |

It intentionally had no inbound HTTP, HTTPS, Docker API, or worker application port. The worker initiates database connections and polls for work; it does not need the public internet to initiate application connections to it.

### If multiple firewalls are attached

DigitalOcean combines rules from every firewall attached to a Droplet. Allow rules are additive, while an applicable deny rule takes precedence. Therefore, attaching an additional broad allow firewall can accidentally widen access. Always inspect the complete set of firewalls attached to a Droplet, not just the one you most recently edited.

DigitalOcean Cloud Firewalls are also separate from host firewalls such as UFW. A rule in one does not automatically appear in the other.

---

## 6. Phase-by-phase reconstruction of the session

### Phase A: created the network perimeter

We first restricted administrative SSH to your public `/32` address. We then gave the app host the public ports it needed and allowed PostgreSQL only from the worker identity/private path.

Why this came first: a freshly created public server is continuously scanned. The firewall reduced exposure before we installed the application.

We created a different firewall for the worker because copying the app rules would have publicly exposed ports the worker does not serve.

### Phase B: pointed the domain at the app host

We created a Cloudflare `A` record:

```text
Name: @
IPv4 address: 192.0.2.10
Proxy status: Proxied
```

`@` means the zone apex: `makeitgreen.dev` itself.

The orange-cloud proxy means browser web traffic flows through Cloudflare before reaching the origin. The DigitalOcean firewall still protects the origin. DNS does not start the application—it only makes a name resolve toward the correct path.

### Phase C: established SSH access safely

The first command without an identity file failed:

```bash
ssh root@192.0.2.10
```

The server required public-key authentication and the client did not offer the correct private key. Supplying it worked:

```bash
ssh -i ~/.ssh/dkey root@192.0.2.10
```

The first-connection authenticity prompt concerned the **server's host key**. Accepting it stored the server identity in your laptop's `known_hosts` file. That protects future connections from silently reaching a different machine at the same address. Ideally, verify a new server's fingerprint through the cloud console before accepting it.

Your `dkey` passphrase protects the private key file on your laptop. It is not the Droplet user's password.

### Phase D: created `deployadmin`

We stopped using direct root login for routine operations and created a named human administrator:

```bash
adduser deployadmin
usermod -aG sudo deployadmin
```

We created `/home/deployadmin/.ssh` with mode `0700`, copied the authorized public keys, and set `authorized_keys` to `0600`. SSH rejects unsafe key-file permissions because another user must not be able to alter which keys are authorized.

We verified:

```bash
ssh -i ~/.ssh/dkey deployadmin@SERVER_IP
sudo whoami
```

The expected output of `sudo whoami` was `root`: the login identity remained `deployadmin`, but that one command ran with administrative privileges.

We repeated this on the worker because Unix user accounts are local to each server. Creating an account on one Droplet does not create it on the other.

### Phase E: updated Ubuntu and rebooted into the new kernel

Ubuntu installed security updates. The OpenSSH package asked whether to replace a locally modified `/etc/ssh/sshd_config`. We chose:

```text
keep the local version currently installed
```

That conservative choice avoided overwriting the cloud image's working SSH configuration while connected remotely. Replacing SSH configuration blindly can lock you out.

The update installed kernel `6.8.0-139-generic`, but the machine was still running `6.8.0-124-generic`. A kernel is loaded at boot, so we rebooted and reconnected. The broken pipe was expected because rebooting terminates SSH.

We verified the new kernel with:

```bash
uname -r
```

### Phase F: installed Docker from Docker's Ubuntu repository

APT can install only packages available from configured repositories. Initially, the Docker repository file was malformed because a pasted multiline command broke shell redirection onto a separate line. The shell tried to execute this path as a command:

```text
/etc/apt/sources.list.d/docker.sources
```

Therefore APT never learned about Docker's repository, and packages such as `docker-ce` had no installation candidate.

We repaired `/etc/apt/sources.list.d/docker.sources` so it contained one valid Deb822 repository stanza:

```text
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
```

Then:

```bash
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io
sudo apt-get install -y docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

`apt-get update` refreshed package metadata. It did not update installed packages by itself. `systemctl enable --now docker` both started Docker immediately and configured it to start after future boots.

We verified both client and server sections in `docker version`, proving the CLI could talk to a running daemon. We also verified the Compose plugin.

We added `deployadmin` to the Docker group and reconnected because group membership is established when a login session starts:

```bash
sudo usermod -aG docker deployadmin
```

Again: Docker group access is effectively administrative access.

### Phase G: prepared separate deployment roots

Both hosts use `/srv/makeitgreen`, but the contents differ.

App host:

```text
/srv/makeitgreen/
├── compose.app.yaml
├── Caddyfile
├── postgres/pg_hba.conf
├── release.env
├── runtime.env
├── secrets/
├── postgres-data/
└── caddy-data/
```

Worker host:

```text
/srv/makeitgreen/
├── compose.worker.yaml
├── release.env
├── runtime.env
├── secrets/
└── run-bundles/
```

The local `scp` commands copied deployment templates to `/home/deployadmin` first. The remote `install` commands then placed them in `/srv/makeitgreen` with deliberate ownership and permissions.

Why not run `scp` while already inside the server? `scp` must read the source files from the machine where those files exist. The repository was on your Mac, so the upload command belonged in a local Mac terminal.

### Phase H: set ownership and modes

Linux access checks use numeric user IDs, group IDs, and permission bits.

Examples:

```text
0:0       root:root
70:70     postgres user/group inside the pinned Alpine PostgreSQL image
65532     non-root application/worker identity inside our images
0700      owner can read/write/enter; nobody else can access
0755      owner can modify; everyone can read/enter
0600      owner can read/write; nobody else can access
0400      owner can read only
0444      everyone can read; nobody can write
0644      owner can write; everyone can read
```

Important nuance: bind mounts preserve host numeric ownership. Container names like `postgres` are conveniences inside the image; the kernel ultimately compares numbers. That is why we asked the pinned PostgreSQL image who its database user was:

```bash
docker run --rm --entrypoint id IMAGE_REFERENCE postgres
```

It returned UID/GID 70, so `postgres-data` and the PostgreSQL-only password/certificate material needed compatible ownership.

The worker's `run-bundles` directory was owned by `65532:65532` because the worker process creates files there while running as that numeric identity.

### Phase I: configured host-specific runtime values

`ip -4 -brief address` displayed the interfaces. On the app host, `eth1` carried `10.20.0.2/20`; on the worker it carried `10.20.0.3/20`. We set:

```text
POSTGRES_BIND_IP=10.20.0.2
```

This made Docker publish PostgreSQL on the app's private VPC interface, not on `0.0.0.0` and not on the public interface.

On the worker, this command found the numeric group owning the Docker socket:

```bash
stat -c '%g' /var/run/docker.sock
```

It returned `987`, so we set:

```text
DOCKER_GID=987
```

The worker container runs as UID/GID 65532, but Compose adds group 987 to the process so it can access the mounted socket. Hard-coding a common number such as 999 would be unreliable because GIDs are host-specific.

`RUN_BUNDLE_DIR` uses the same absolute path on the host and inside the worker container. This matters because the worker asks the **host daemon** to mount that path into child containers. The daemon interprets mount source paths in the host's filesystem namespace.

### Phase J: distinguished `runtime.env` from `release.env`

`runtime.env` contains host/deployment configuration such as:

- domain name;
- private bind address;
- Docker socket GID;
- memory and concurrency limits;
- request and admission limits.

`release.env` contains immutable image references selected from one successful release manifest.

Keeping them separate answers two different questions:

```text
runtime.env: How should this host run the system?
release.env: Exactly which built release should this host run?
```

We never mix image references from different release manifests. The control plane and worker compare their embedded source commit SHA. A mixed release deliberately fails exact-version readiness.

### Phase K: prepared PostgreSQL safely

We pulled the exact PostgreSQL image digest, checked its runtime UID, and assigned the persistent data directory to UID/GID 70.

We verified the server certificate:

```bash
openssl verify -CAfile postgres_ca.crt postgres_server.crt
openssl x509 -in postgres_server.crt -noout -ext subjectAltName
```

The first command proved the certificate chained to our trusted CA. The second proved it named `postgres` and `10.20.0.2`.

We started PostgreSQL alone first:

```bash
docker compose --env-file release.env --env-file runtime.env \
  -f compose.app.yaml up -d postgres
```

This isolated database initialization from the rest of startup. Compose reported `healthy`, meaning the configured `pg_isready` health check passed.

### Phase L: applied migrations and created runtime roles

Migrations are versioned schema changes. Hosted Mode intentionally does not mutate its schema while serving requests.

We copied migrations `001` through `007`, applied them in order with the schema-owner role, and queried:

```sql
SELECT version
FROM greenline_schema_version
WHERE singleton = TRUE;
```

The answer `7` proved the database schema matched the application release's expectation.

We then created two runtime roles:

- `greenline_api` for the control plane;
- `greenline_worker` for the execution worker.

They received different, least-privilege grants. The powerful schema-owner credentials were not placed in runtime containers.

When the API password was regenerated after the first role bootstrap, we reran the bootstrap script so PostgreSQL's stored role password and the secret file matched. A connection URL is useless if its password no longer matches the role.

### Phase M: constructed database URL secret files

The URL format was:

```text
postgresql://ROLE:PASSWORD@HOST:5432/greenline?sslmode=verify-full&sslrootcert=/run/secrets/postgres_ca
```

The first multiline shell attempt failed because a blank line ended a backslash continuation. The shell then treated the quoted URL as a command, producing `not found`.

The reliable recovery was to enter a root shell, change to the exact directory, build the URL in small variables, write it with `printf`, unset temporary shell variables, and verify only metadata with `stat`.

We did **not** print the secret URL to the terminal.

We assigned runtime secret ownership to UID/GID 65532 and used mode `0400`, allowing the intended container identity to read it but preventing other users from doing so.

### Phase N: transferred the minimum worker secrets

The worker needed only:

```text
postgres_ca.crt
worker_database_url
security_log_hmac_key
```

We staged those files temporarily from app server to Mac to worker server, installed them into the worker's protected secret directory, and deleted every staging copy afterward.

This was a manual bootstrap mechanism, not an ideal long-term secret-delivery system. The key principle was minimum distribution: the worker never received the Clerk secret, API database URL, database owner password, or PostgreSQL server private key.

The CA certificate used mode `0444` because it is public trust material, not a private key. The URL and HMAC key used `0400`.

### Phase O: authenticated to the private GitHub Container Registry

GHCR rejected the first pull with `unauthorized` because the images were private and Docker had no credentials for `ghcr.io`.

We used a hidden prompt and `--password-stdin`:

```bash
read -rsp 'Paste GHCR token (hidden): ' GHCR_TOKEN
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u USERNAME --password-stdin
unset GHCR_TOKEN
```

This avoided putting the token directly into command history or process arguments. Docker warned that credentials were stored unencrypted in root's Docker configuration. That file must remain protected. A credential helper or short-lived deployment credential would be a future improvement.

If a real token is ever pasted into chat, committed, printed, or exposed in terminal history, revoke it and create a new least-privilege token.

### Phase P: pulled and started the worker

The worker has three relevant images:

1. the long-running execution-worker image;
2. the disposable Python execution image;
3. the disposable Node execution image.

Compose automatically pulled the service image, while we explicitly pre-pulled both child execution images. Pre-pulling prevents the first learner run from waiting on a large image download and lets the worker health check verify that the required immutable images exist.

`docker compose up -d` created the worker network and started the container. `docker compose ps` showed `healthy` and no public port.

### Phase Q: started the public application stack

On the app host we pulled:

- the control plane;
- Caddy;
- PostgreSQL.

We wrote the production Clerk secret into a protected file and validated its `sk_live_` format without printing the value.

Before startup, we ran:

```bash
docker compose --env-file release.env --env-file runtime.env \
  -f compose.app.yaml config --quiet
```

This rendered and validated Compose configuration. No output meant valid syntax/configuration; it did not mean the services were already healthy.

We started the control plane and waited for PostgreSQL health. Then we started Caddy, whose dependency required a healthy control plane.

The resulting exposure was:

```text
Caddy:        host ports 80 and 443
Control Plane: container port 8000 only; no host-public mapping
PostgreSQL:   10.20.0.2:5432 only
Worker:       no application port
```

### Phase R: verified health and negative network properties

The public health checks returned HTTP 200:

```text
/health/live     process is alive
/health/ready    dependencies are ready
/health/release  exact release and worker compatibility are ready
```

`/health/release` was especially valuable. It reported:

- control-plane source SHA;
- number of live workers;
- number of workers matching the exact release;
- Python execution image digest;
- Node execution image digest.

We also ran negative `nc` tests against public IPs. Timeouts on PostgreSQL, control-plane port 8000, and Docker ports 2375/2376 were the desired result. A secure deployment must test what is **not** reachable, not only what is reachable.

---

## 7. The blank editor incident

### Symptom

After an invited user signed in, the challenge catalog loaded and the workspace file list loaded, but the editor stayed dark with:

```text
Loading...
```

This told us several things were already working:

- DNS and HTTPS;
- Cloudflare and Caddy routing;
- the React application shell;
- Clerk authentication;
- challenge API calls;
- database-backed user state.

The failure was narrower: the code editor itself had not initialized.

### Root cause

The frontend used `@monaco-editor/react`. Its default loader contained a jsDelivr URL for Monaco assets:

```text
https://cdn.jsdelivr.net/npm/monaco-editor/.../vs
```

Our production Content Security Policy intentionally allowed scripts only from the site itself and specific Clerk/Cloudflare domains. `cdn.jsdelivr.net` was not permitted.

So these two independently reasonable choices conflicted:

```text
Monaco wrapper default: fetch editor runtime from an external CDN
Production CSP:         reject scripts not explicitly trusted
```

The browser obeyed the CSP, Monaco never completed initialization, and the React wrapper remained on its default loading screen.

### Correct fix

We did not weaken the CSP by adding a broad third-party script source. Instead, we bundled Monaco with the application.

We added `monaco-editor` as an exact direct dependency and created `frontend/src/monacoSetup.ts`. That module:

1. imports the local Monaco package;
2. imports editor, JSON, CSS, HTML, and TypeScript workers through Vite's `?worker` feature;
3. defines `self.MonacoEnvironment.getWorker` to route language labels;
4. calls `loader.config({ monaco })` before the application renders.

Then `main.tsx` imports the setup module before rendering any editor component.

The important relationship is:

```text
Before:
browser -> jsDelivr Monaco loader -> blocked by CSP -> permanent Loading...

After:
browser -> /assets/index-<hash>.js
        -> /assets/editor.worker-<hash>.js
        -> /assets/json.worker-<hash>.js
        -> /assets/css.worker-<hash>.js
        -> /assets/html.worker-<hash>.js
        -> /assets/ts.worker-<hash>.js
        -> all same-origin and allowed -> editor renders
```

### Regression test

We added a focused Vitest regression test that verifies:

- the React wrapper receives the locally imported Monaco instance;
- each supported language label creates the correct bundled worker;
- other languages fall back to the general editor worker.

The test failed before the setup module existed and passed after the implementation. That is evidence that the test covers the missing behavior rather than merely observing the final implementation.

### Local verification

We ran:

```text
npm test       all tests passed
npm run lint   passed
npm run build  passed
```

The Vite build emitted five same-origin worker assets. The large TypeScript worker explains much of the increased bundle weight; that is a future performance optimization, not a correctness failure.

The editor fix was committed as:

```text
c79d468 fix(frontend): self-host Monaco editor assets
```

---

## 8. Why the first release pipeline failed after the editor fix

The code tests passed, but the image security gate discovered two new fixable HIGH vulnerabilities in the `libpcre2-8-0` package inherited from the pinned Debian Python base image.

This is an important production lesson: the same source can pass yesterday and fail today because vulnerability intelligence and distribution security packages change.

The base image digest was still the same and contained version `10.42-1`. Debian's repository offered the patched `10.42-1+deb12u1`.

We added a narrow package upgrade to the Debian-based runtime Dockerfiles:

```dockerfile
RUN apt-get update && \
    apt-get install --only-upgrade --yes libpcre2-8-0 && \
    rm -rf /var/lib/apt/lists/*
```

Why each part matters:

- `apt-get update` obtains current package metadata.
- `--only-upgrade` upgrades an already installed package rather than introducing unrelated packages.
- `--yes` makes the image build non-interactive.
- removing `/var/lib/apt/lists/*` keeps the final image layer smaller.

We built all affected images locally and queried the installed package version. Each reported the fixed version.

The security fix was committed as:

```text
bc2f9e8 fix(images): install patched PCRE2 runtime
```

---

## 9. What the GitHub Actions pipeline guaranteed

The successful workflow run was `34685430678` for full source SHA:

```text
bc2f9e819b47e74f01c7416fdc10fbdc34135c03
```

The workflow performed independent gates:

1. backend tests;
2. challenge invariant validation;
3. frontend tests, lint, and production build;
4. production identity-variable validation;
5. builds of all four runtime images;
6. fixable HIGH/CRITICAL vulnerability scanning;
7. hosted process-role smoke tests;
8. SBOM and maximum-provenance export;
9. verification that publishable archives contained the same runtime manifests that were scanned;
10. publication to GHCR without rebuilding;
11. generation of one release manifest containing all four immutable digests.

"Publish without rebuilding" is meaningful. If CI scanned image A and later rebuilt image B during publishing, subtle input changes could make B differ from what was scanned. This pipeline publishes the verified OCI archives.

The successful manifest selected:

```text
control-plane:
ghcr.io/oseni99/makeitgreen-control-plane@sha256:6bbec36b85cdfa6b981f2c0fe7b023e24d5d98b9468115a2f88c16d96dd992d1

execution-worker:
ghcr.io/oseni99/makeitgreen-execution-worker@sha256:312ce0a03cbcc7cc83931ff3f6af760476d2e19cd0bb6f4bb5df626dcf8352f1

python-execution:
ghcr.io/oseni99/makeitgreen-python-execution@sha256:b71f68985d6968d305b855bf72160a7e0217e962e079ca938a87c894b8be91c7

node-execution:
ghcr.io/oseni99/makeitgreen-node-execution@sha256:f92c102ea7fd7bcbd4af79cc0da2e7486c1d4341a684ef7b5cbdd45e3cecd6e4
```

These values belong together. Think of the manifest as a release bill of materials.

---

## 10. How we rolled out the fix

We used a staged manual rollout.

### Step 1: backed up current configuration

On each host we copied `release.env` to:

```text
release.env.before-bc2f9e8
```

That provided a fast configuration rollback point.

### Step 2: updated the worker's three references

We replaced the worker service, Python execution, and Node execution digests in the worker `release.env`. We printed only non-secret release data to verify exact values.

### Step 3: validated and pre-pulled

`docker compose config --quiet` caught configuration errors without changing running containers. We pulled all three new worker-side images while the old worker kept running.

### Step 4: updated and pre-pulled the app

We replaced only the control-plane digest. Caddy and PostgreSQL stayed pinned to their existing external image digests. Again, we validated Compose and pulled without changing the running app.

### Step 5: switched the worker

We force-recreated only the execution-worker service. This began the brief window where the old control plane and new worker had different release SHAs.

### Step 6: switched the control plane and Caddy

We force-recreated the two public-facing services together with `--no-deps`, leaving healthy PostgreSQL untouched. `--wait --wait-timeout 60` made Compose wait for health instead of returning immediately after process creation.

Restarting Caddy with the control plane also ensured it resolved/routed to the new container endpoint.

### Step 7: verified exact-version readiness

`https://makeitgreen.dev/health/release` returned HTTP 200 and reported:

```text
status: ready
source_sha: bc2f9e819b47e74f01c7416fdc10fbdc34135c03
live_workers: 1
matching_workers: 1
worker source_sha: bc2f9e819b47e74f01c7416fdc10fbdc34135c03
```

We fetched each emitted Monaco worker URL and received HTTP 200. Finally, a browser hard refresh loaded the new hashed frontend asset, and the source code appeared in the editor.

That browser screenshot was the end-to-end proof. It tested more than container health: Cloudflare, Caddy, frontend assets, authentication state, API data, CSP, Vite worker URLs, Monaco initialization, and rendering all worked together.

---

## 11. What the important commands mean

### `ssh -i ~/.ssh/dkey user@host`

- `ssh`: create an encrypted remote shell connection;
- `-i`: use this private identity key;
- `user@host`: request login as that user on that host.

### `scp -i KEY SOURCE user@host:DESTINATION`

Copy files over SSH. Run it on the machine that can read `SOURCE`.

### `sudo -i`

Open a root login shell. The prompt changes from `$` to `#`. Every subsequent command is fully privileged until `exit`. Use it carefully.

### `install -d -o UID -g GID -m MODE PATH`

Create a directory with explicit owner, group, and mode. This is more deterministic than `mkdir` followed by separate `chown` and `chmod` commands.

### `stat -c '%u:%g %a %s %n' FILE`

Print numeric owner, group, permission mode, size, and name without revealing file contents. This is ideal for verifying secrets safely.

### `sed -i 's|^NAME=.*|NAME=value|' FILE`

Edit a matching configuration line in place. The anchor `^` means beginning of line. Always print the non-secret file afterward and retain a backup.

### `docker pull IMAGE@sha256:DIGEST`

Download a specific immutable image. It does not start a container.

### `docker compose config --quiet`

Resolve the Compose file, environment substitutions, and model validation. It does not prove runtime dependencies or network reachability.

### `docker compose up -d`

Reconcile actual containers toward the desired Compose state and return in detached mode.

### `--force-recreate`

Replace a container even if Compose might otherwise consider it unchanged.

### `--no-deps`

Do not start/recreate dependency services while acting on the selected services. We used it to avoid touching PostgreSQL during the frontend/control-plane rollout.

### `--wait --wait-timeout 60`

Wait until selected services are running/healthy, failing after the timeout rather than claiming success merely because the processes started.

### `docker compose ps`

Show container state, health, image, and published ports. It is a snapshot, not a log.

### `docker compose logs --tail 100 SERVICE`

Inspect recent service output when a container is unhealthy or repeatedly restarting.

### `curl -i --max-time 15 URL`

Make an HTTP request, show response headers, and stop waiting after 15 seconds.

### `nc -vz HOST PORT`

Attempt a TCP connection without speaking the application protocol. A success means the port is reachable, not that the application is correct. A timeout on an intentionally private port can be a successful security test.

---

## 12. A staff-engineer troubleshooting method

When production is broken, avoid random commands. Use this order.

### 1. State the symptom precisely

Bad:

```text
The app is broken.
```

Good:

```text
After authentication, the challenge workspace and file list render, but every
file editor remains on the Monaco wrapper's Loading placeholder.
```

Precision tells you which layers are already working.

### 2. Draw the request path

For the editor issue:

```text
browser -> Cloudflare -> Caddy -> control plane -> HTML/JS -> Monaco workers
```

Then ask where the last confirmed success occurred.

### 3. Check cheap evidence before changing state

Examples:

- health endpoints;
- browser console and Network panel;
- `docker compose ps`;
- `docker compose logs`;
- rendered Compose config;
- file ownership metadata;
- current image IDs/digests;
- listening sockets;
- firewall attachments.

### 4. Form a falsifiable hypothesis

Our hypothesis was not "Monaco is buggy." It was:

```text
The React wrapper is attempting to load Monaco from jsDelivr, and the production
CSP rejects that source, so loader initialization never resolves.
```

Evidence that would falsify it: no CDN request, no CSP violation, or successful loader initialization.

### 5. Prefer the fix that preserves the security boundary

We could have added jsDelivr to `script-src`, but self-hosting eliminated the runtime third-party dependency and preserved the restrictive CSP.

### 6. Add a regression test

Capture the behavior that was missing, not an incidental implementation detail.

### 7. Validate from narrow to broad

```text
targeted test -> all tests -> lint -> production build -> image build
-> vulnerability scan -> smoke test -> publish -> staged rollout
-> health endpoint -> browser behavior
```

### 8. Keep rollback available until verification finishes

Do not delete old image references or backups before the new release is healthy.

---

## 13. Rollback procedure for this release

Use rollback only if the new release is unhealthy. Preserve logs first when possible.

The configuration backups are:

```text
/srv/makeitgreen/release.env.before-bc2f9e8
```

High-level rollback order:

1. restore the worker's previous `release.env`;
2. validate and pull the old worker/execution images if missing;
3. recreate the worker;
4. restore the app's previous `release.env`;
5. validate and pull the old control-plane image if missing;
6. recreate control plane and Caddy;
7. verify `/health/release` reports one matching old-release worker;
8. investigate the failed release off the production path.

Do not roll PostgreSQL backward merely because an application container failed. Database rollback is a separate, higher-risk operation and depends on whether migrations were backward-compatible. This editor release had no new migration.

---

## 14. What to monitor now

### After every deployment

- `docker compose ps` on both hosts;
- app and worker logs for startup errors;
- `/health/live`;
- `/health/ready`;
- `/health/release`;
- one authenticated challenge load;
- one Python test run;
- one JavaScript test run;
- public negative-port checks;
- disk and memory usage.

### Regularly

- PostgreSQL backups and restore drills;
- Droplet disk usage, especially Docker layers and PostgreSQL data;
- worker OOM/restart events;
- certificate renewal and TLS errors;
- failed authentication/rate-limit events;
- GHCR credential/token expiry;
- OS security updates and required reboots;
- CI vulnerability scan failures;
- Cloudflare and DigitalOcean account MFA/access review.

Health checks are necessary but not sufficient. A healthy process can still have a broken user workflow, as the Monaco incident demonstrated.

---

## 15. What should be automated next

Manual deployment taught us the system, but repetition should move into automation.

Recommended order:

1. **Documented one-command preflight.** Run deployment validation, verify required secret metadata, available disk/memory, VPC addresses, Docker GID, and registry access.
2. **Configuration management.** Use Ansible or cloud-init to create users, install Docker, place system files, set ownership, and configure services reproducibly.
3. **Infrastructure as code.** Use Terraform/OpenTofu for Droplets, VPC membership, tags, firewalls, reserved IP strategy, and DNS inputs.
4. **Secret management.** Replace Mac-mediated staging with a proper secret manager or encrypted deployment channel and short-lived access.
5. **Automated rollout agent.** Consume one signed release manifest, stage both hosts, coordinate version switches, verify `/health/release`, and automatically restore previous digests if necessary.
6. **Observability.** Centralize structured logs, metrics, alerts, disk monitoring, and worker job latency/error rates.
7. **Backup automation.** Encrypt PostgreSQL backups, store them off-host, define retention, and perform scheduled restore tests.
8. **SSH hardening.** After verification, disable routine direct root SSH, restrict allowed users, consider hardware-backed keys, and keep console recovery available.
9. **Performance optimization.** Lazy-load Monaco and language workers so catalog/landing users do not download the large editor code before opening a workspace.

Automation is not merely about speed. Its main value is reducing configuration drift and making every change reviewable and repeatable.

---

## 16. Common mistakes from this session and the lesson from each

| Mistake or surprise | What it meant | General lesson |
|---|---|---|
| SSH timed out or was denied | firewall/key selection differed from expectation | Separate network reachability from authentication |
| SSH worked only with `-i ~/.ssh/dkey` | the correct key was not the default offered key | Know which credential the client is using |
| `Permission denied (publickey)` | server was reachable but rejected authentication | This is not a firewall failure |
| Reboot caused broken pipe | SSH process was terminated during reboot | Expected disconnects are not deployment failures |
| Docker packages had no candidate | Docker APT repository was not installed correctly | Verify generated config files before continuing |
| Multiline command broke at a blank line | shell continuation ended unexpectedly | Prefer short, paste-safe commands for manual production work |
| `cd secrets` was denied | directory was intentionally mode 0700 and root-owned | Access denial can prove the security control is working |
| Compose env file was denied | root-owned mode 0600 file was intentionally unreadable | Use controlled privilege; do not weaken permissions reflexively |
| GHCR pull was unauthorized | private registry needed authentication | Registry access is separate from server/Docker access |
| Public `nc` timed out | private ports were blocked as designed | Negative tests are part of verification |
| CI failed after code tests passed | supply-chain security gate found a new CVE | Passing unit tests does not make an image releasable |
| Browser showed `Loading...` while health was green | process health missed a frontend runtime dependency | Verify real user journeys after deployment |
| Hard refresh fixed the final stale view | existing tab was still running old JavaScript | Containers can be current while a browser tab is not |

---

## 17. Questions you should now be able to answer

Use these as a self-test. If an answer is fuzzy, return to the linked section.

1. Why did we use a public `/32` address for SSH instead of your laptop's Wi-Fi address?
2. Why can the worker reach PostgreSQL at `10.20.0.2:5432` while your laptop cannot reach the public app IP on port 5432?
3. Why are the app and worker firewalls different?
4. Why does the worker expose no application port?
5. What is the difference between an image and a container?
6. What is the difference between `docker pull` and `docker compose up -d`?
7. Why is `@sha256:...` safer than `:latest`?
8. Why must all four release image references come from one manifest?
9. Why did we query the PostgreSQL image's UID instead of assuming it?
10. Why can `deployadmin` run Docker without `sudo`, and why is that powerful?
11. Why is `worker_database_url` on the worker but `clerk_secret_key` is not?
12. What does `sslmode=verify-full` add beyond encryption?
13. Why did schema migrations run before the control plane started?
14. Why did `/health/release` check matching workers, not merely live workers?
15. Why did the editor fail even while `/health/ready` returned 200?
16. Why was self-hosting Monaco preferable to weakening CSP?
17. Why did we pull images before recreating containers?
18. What exact evidence proved the incident was resolved?

Short answers are included below. Try first without looking.

<details>
<summary>Answer key</summary>

1. The cloud firewall sees your network's public NAT address, not the laptop's private LAN address; `/32` permits exactly that IPv4 source.
2. PostgreSQL is bound to a VPC interface and the firewall permits the worker identity/path, not arbitrary public clients.
3. The app serves public HTTPS and private PostgreSQL; the worker only needs restricted administration and outbound connections.
4. It polls PostgreSQL and starts local child containers; no client initiates an application connection to it.
5. An image is the immutable template; a container is a running process created from it.
6. Pull downloads bytes; `up` reconciles/runs configured containers.
7. A digest identifies exact content; a tag can be moved to different content.
8. The system enforces exact release compatibility, and mixed code/execution images may violate contracts.
9. Bind-mount access uses numeric IDs, and image user IDs can differ between images.
10. Its login session includes the group that owns the daemon socket; daemon control is effectively root access.
11. Each host receives only secrets required for its role.
12. It verifies the trusted signing CA and destination identity/hostname in addition to encrypting traffic.
13. The application expects an exact schema version and must not perform DDL while serving traffic.
14. A live worker from another code release may not understand the same job or execution contract.
15. Server processes and dependencies were healthy, but the browser blocked a third-party editor asset under CSP.
16. It preserved the restrictive policy and removed a runtime third-party dependency.
17. It shortened downtime and surfaced registry/download errors before touching healthy containers.
18. CI passed, images published, both hosts reported the same release SHA, worker assets returned HTTP 200, and the authenticated browser rendered source code.

</details>

---

## 18. Repository map for this deployment

Use these files when connecting concepts to implementation:

| Concern | Repository file |
|---|---|
| Overall deployment instructions | [`deploy/README.md`](../deploy/README.md) |
| App services and security controls | [`deploy/app/compose.app.yaml`](../deploy/app/compose.app.yaml) |
| Worker service and Docker socket | [`deploy/worker/compose.worker.yaml`](../deploy/worker/compose.worker.yaml) |
| Browser run submission and polling | [`frontend/src/pages/Workspace.tsx`](../frontend/src/pages/Workspace.tsx) |
| Hosted Run Job API endpoints | [`backend/app.py`](../backend/app.py) |
| PostgreSQL queue leases, fences, and heartbeats | [`backend/run_coordination.py`](../backend/run_coordination.py) |
| Disposable-container isolation policy | [`backend/runner.py`](../backend/runner.py) |
| Worker runtime composition | [`backend/worker.py`](../backend/worker.py) |
| TLS edge, reverse proxy, CSP | [`deploy/app/Caddyfile`](../deploy/app/Caddyfile) |
| PostgreSQL client policy | [`deploy/app/postgres/pg_hba.conf`](../deploy/app/postgres/pg_hba.conf) |
| App host configuration template | [`deploy/app/runtime.env.example`](../deploy/app/runtime.env.example) |
| Worker host configuration template | [`deploy/worker/runtime.env.example`](../deploy/worker/runtime.env.example) |
| Control-plane image build | [`Dockerfile`](../Dockerfile) |
| Worker image build | [`Dockerfile.worker`](../Dockerfile.worker) |
| Monaco self-hosting setup | [`frontend/src/monacoSetup.ts`](../frontend/src/monacoSetup.ts) |
| Frontend entry point | [`frontend/src/main.tsx`](../frontend/src/main.tsx) |
| Monaco regression test | [`frontend/tests/monaco-self-hosting.test.tsx`](../frontend/tests/monaco-self-hosting.test.tsx) |
| Database migration contract | [`backend/migrations/README.md`](../backend/migrations/README.md) |
| Deployment validator | [`scripts/validate_deployment.py`](../scripts/validate_deployment.py) |
| Main CI/release pipeline | [`../../.github/workflows/greenline.yml`](../../.github/workflows/greenline.yml) |
| Promotion/rollback workflow | [`../../.github/workflows/promote-greenline.yml`](../../.github/workflows/promote-greenline.yml) |

---

## 19. Final mental model

What we did was not "type a large pile of commands until a website appeared."

We assembled and verified a chain of explicit contracts:

```text
Identity contract
  SSH key -> deployadmin -> sudo -> controlled administrator access

Network contract
  public web only -> private database path -> no public worker/Docker ports

Runtime contract
  Compose files -> exact mounts/networks/users/limits/health checks

Secret contract
  minimum secrets -> correct host -> correct numeric owner -> read-only mode

Database contract
  TLS identity -> SCRAM role -> least privilege -> schema version 7

Release contract
  one Git SHA -> four scanned image digests -> one release manifest

Readiness contract
  healthy control plane -> healthy database -> live matching worker

Browser contract
  CSP-approved same-origin assets -> Monaco workers initialize -> code renders
```

Production engineering is largely the discipline of making these contracts explicit, verifying each one independently, and refusing to call the deployment complete until the full user journey also works.
