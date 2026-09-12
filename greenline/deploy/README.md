# MakeItGreen deployment bundle

This directory contains two independent Docker Compose deployments:

- `app/`: Caddy, the public Control Plane, and PostgreSQL.
- `worker/`: the non-HTTP execution worker. Disposable Challenge Run
  containers are created by the worker through that host's Docker socket.

Do not copy the application deployment to the worker or mount the Docker socket
on the application host. The split is the beta trust boundary.

## 1. Prepare each host

Create `/srv/makeitgreen`, copy only that host's deployment files into it, and
create the directories below.

Application host:

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

On the worker host, provision Run Bundle storage for the worker's numeric UID
before starting it:

```bash
sudo install -d -o 65532 -g 65532 -m 0700 /srv/makeitgreen/run-bundles
```

The bind mount preserves host ownership. A root-owned directory prevents the
worker's storage readiness check from succeeding.

Copy each `*.env.example` to the corresponding ignored `*.env` file. Take the
four MakeItGreen image references from one successful GitHub release manifest;
never mix commits or remove `@sha256:...`. The Caddy and PostgreSQL references
are already pinned to immutable multi-platform indexes.

## 2. Create secrets

The application host requires:

```text
secrets/clerk_secret_key
secrets/api_database_url
secrets/security_log_hmac_key
secrets/postgres_admin_password
secrets/postgres_server.crt
secrets/postgres_server.key
secrets/postgres_ca.crt
```

The worker host requires only:

```text
secrets/worker_database_url
secrets/security_log_hmac_key
secrets/postgres_ca.crt
```

The two `security_log_hmac_key` copies must contain the same random value of at
least 32 bytes. The API and worker database URLs use separate least-privilege
roles. Both URLs must require TLS and verify `postgres_ca.crt`; for example:

```text
postgresql://ROLE:PASSWORD@HOST:5432/greenline?sslmode=verify-full&sslrootcert=/run/secrets/postgres_ca
```

The PostgreSQL server certificate must be valid for `postgres` and the app
Droplet's private VPC address. Never put the schema-owner URL in either runtime
secret.

Secret locations are deliberately fixed under each deployment's `./secrets`
directory. They cannot be relocated through shell or env-file interpolation.

Compose file secrets are bind mounts. On the application host, make API files
owned by UID/GID `65532:65532` and the PostgreSQL password/key/cert files owned
by the numeric `postgres` user/group from the pinned image. On the worker host,
make all three files owned by `65532:65532`. Make secret directories `0700`,
private keys/passwords `0400`, and certificates `0444`. Verify the image UID
instead of assuming it after changing the PostgreSQL image.

## 3. Validate before starting

Run the repository validator from a trusted checkout, pointing it at the two
prepared host directories (or validate each copied directory before upload):

```bash
python scripts/validate_deployment.py \
  --app-root /path/to/app \
  --worker-root /path/to/worker
```

It checks both the env files and the effective rendered Compose settings,
including shell environment overrides. It rejects mutable image tags, inconsistent admission limits, a public
PostgreSQL bind, a mismatched Run Bundle mount, leaked Clerk credentials, or a
Docker socket on the application host. It also renders both Compose models via
`docker compose config`.

## 4. Start in order

On the application host:

```bash
docker compose --env-file release.env --env-file runtime.env \
  -f compose.app.yaml pull
docker compose --env-file release.env --env-file runtime.env \
  -f compose.app.yaml up -d postgres
```

Apply migrations `001` through `007` with the schema owner, create the separate
runtime roles, and write the final runtime URLs before starting the Control
Plane and Caddy. Then:

```bash
docker compose --env-file release.env --env-file runtime.env \
  -f compose.app.yaml up -d
curl --fail https://makeitgreen.dev/health/ready
curl --fail https://makeitgreen.dev/health/release
```

On the worker host, pre-pull both execution images before the worker starts:

```bash
docker compose --env-file release.env --env-file runtime.env \
  -f compose.worker.yaml pull
docker pull "$(sed -n 's/^PYTHON_EXECUTION_IMAGE=//p' release.env)"
docker pull "$(sed -n 's/^NODE_EXECUTION_IMAGE=//p' release.env)"
docker compose --env-file release.env --env-file runtime.env \
  -f compose.worker.yaml up -d
```

The worker exposes no port. Its image healthcheck verifies Docker, PostgreSQL,
the immutable execution images, and the release contract. Finally rerun
`/health/release`; it is healthy only when a matching worker heartbeat exists.

The PostgreSQL port is bound only to `POSTGRES_BIND_IP`. Keep the DigitalOcean
Cloud Firewall rule limited to tagged worker Droplets even though `pg_hba.conf`
also rejects every non-TLS connection. Inside the application deployment,
PostgreSQL uses a separate bridge network; only the Control Plane
joins both the proxy and database networks. The database network must allow
external connectivity so Docker can publish PostgreSQL's private-IP port for
the worker hosts. The private bind, TLS, and Cloud Firewall enforce that boundary.
