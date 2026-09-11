# Moving the MakeItGreen database to Neon after beta

This runbook records one deliberate lifecycle decision:

- **Invited beta:** self-hosted PostgreSQL on the DigitalOcean application
  Droplet, reachable by workers only through the private VPC.
- **Public launch:** managed PostgreSQL on Neon, after a rehearsed cutover and
  an observation period.

The move is an infrastructure migration, not an application rewrite. Hosted
Mode reads one PostgreSQL URL through `GREENLINE_DATABASE_URL_FILE`; the
Control Plane and workers do not depend on a DigitalOcean database API.

## Connection contract

Keep three credentials with different purposes:

| Credential | Used by | Beta destination | Public-launch destination |
|---|---|---|---|
| Control Plane runtime | Control Plane only | DigitalOcean private PostgreSQL URL | Neon pooled TLS URL |
| Worker runtime | worker pool only | DigitalOcean private PostgreSQL URL | Neon pooled TLS URL |
| Schema owner | operator tooling only | DigitalOcean direct URL | Neon direct TLS URL |

The runtime credentials must not own the schema or create roles. The schema
owner must not be mounted into either long-lived runtime. With Neon, the pooled
hostname contains `-pooler`; the direct hostname does not. Use the direct URL
for `pg_dump`, `pg_restore`, `psql` migrations, and administrative checks.

Keep the Neon database in the closest available region to the DigitalOcean
application and worker hosts. Require TLS in every Neon URL. Use
`sslmode=verify-full` where the deployed PostgreSQL client and certificate
configuration support it; never weaken production URLs below
`sslmode=require`.

## Make the beta migration-ready

Before inviting beta learners:

1. Record the source value of `SHOW server_version;` with the deployment
   inventory. Create the later Neon project on the same PostgreSQL major
   version.
2. Keep the database hostname out of images and Compose manifests. Mount only
   `api_database_url` and `worker_database_url` secret files.
3. Use separate runtime and schema-owner roles from the first deployment.
4. Produce scheduled encrypted, off-host custom-format dumps. Use current
   PostgreSQL client tools and exclude source ownership and ACLs:

   ```bash
   pg_dump --format=custom --no-owner --no-acl \
     --file makeitgreen-beta.dump "$SOURCE_DATABASE_URL"
   ```

5. Restore a dump into a disposable database and run the application smoke
   test before treating the backup process as working.

The current schema uses built-in PostgreSQL features and declares no
`CREATE EXTENSION` dependency. Recheck the migrations before the cutover in
case that changes during beta.

## Rehearse before the public-launch cutover

Perform the complete procedure against a disposable Neon project while the
DigitalOcean beta database remains authoritative:

1. Create Neon on the same PostgreSQL major version and in the closest region.
2. Import a recent beta dump through the Neon direct URL:

   ```bash
   pg_restore --verbose --exit-on-error --no-owner \
     --dbname "$NEON_DIRECT_DATABASE_URL" makeitgreen-beta.dump
   ```

3. Recreate the separately managed Control Plane and worker roles and their
   least-privilege grants. Roles and source ACLs are intentionally not imported.
4. Run [`scripts/database_cutover_check.sql`](scripts/database_cutover_check.sql)
   against both databases. If beta writes continue during rehearsal, source
   counts can advance after the dump snapshot; use a short rehearsal write
   freeze when an exact count comparison is required.
5. Start a staging Control Plane and worker with their Neon pooled URLs. Verify
   `/health/ready`, `/health/release`, sign-in, workspace persistence, one
   Python run, one Node run, history, reset, and audit recording.
6. Record restore time, smoke-test results, connection usage, and any manual
   correction. Repeat until the procedure is uneventful.

## Verification

Run the checked-in verification script through direct read-only administrative
connections. Save both outputs with the cutover record:

```bash
psql "$SOURCE_DATABASE_URL" --file scripts/database_cutover_check.sql \
  > source-database-check.txt
psql "$NEON_DIRECT_DATABASE_URL" --file scripts/database_cutover_check.sql \
  > neon-database-check.txt
```

The script fails unless the schema is currently version `7`, every public
constraint is validated, and no Run Job remains queued or running. During the
final frozen-source cutover, every row count and identity-sequence value must
match. A dump restore carries identity-sequence state, but the staging smoke
test must still create new run and product-event rows to prove that new
identities do not collide.

## Final cutover

Use a scheduled maintenance window. Do not accept writes in two databases.

1. Put Caddy into the prepared maintenance response so no new API mutation can
   enter.
2. Let already-running Challenge Runs finish. Require this query to return no
   rows, then stop every execution worker:

   ```sql
   SELECT id, status FROM run_jobs WHERE status IN ('queued', 'running');
   ```

3. Stop the Control Plane and verify that no runtime-role connections remain in
   `pg_stat_activity`. The DigitalOcean database is now the frozen source.
4. Create the final custom-format dump with `--no-owner --no-acl` and retain its
   checksum with the cutover record:

   ```bash
   sha256sum makeitgreen-beta.dump > makeitgreen-beta.dump.sha256
   ```
5. Restore into the empty production Neon database through its direct URL.
6. Recreate runtime roles/grants and run all verification queries. Do not apply
   migrations unless Neon is behind the source schema version; a restored
   current database already contains the schema.
7. Replace `api_database_url` and `worker_database_url` with their respective
   Neon pooled TLS URLs. Do not place the direct schema-owner URL there.
8. Start workers, then the Control Plane. Require `/health/ready` and
   `/health/release` to pass and repeat the end-to-end Python and Node smoke
   runs.
9. Reopen Caddy only after verification passes. Record the time of the first
   accepted Neon write and observe database errors, connection usage, queue
   wait, and execution completion closely.

## Rollback boundary

Before public traffic is reopened, rollback means restoring the two original
DigitalOcean secret files and restarting workers and the Control Plane. This is
safe because the source has remained frozen and Neon has accepted no user
writes.

After the first Neon write, do **not** point the application back to the old
database: doing so would discard post-cutover data. A later rollback requires a
separate reverse synchronization or a restore from Neon. Keep the old
DigitalOcean database stopped and access-restricted for a short, defined
retention window, then destroy it only after the owner approves the cutover and
the retained backup has passed a restore check.

## Public-launch gate

The database gate passes only when all of the following are recorded:

- same-major-version rehearsal completed;
- final source writes frozen and active Run Jobs drained;
- final dump checksum retained;
- schema version, row counts, and constraints verified;
- both execution runtimes pass against Neon;
- runtime secrets contain pooled URLs and the migration role remains separate;
- backup/restore and alerting are enabled for Neon;
- rollback boundary and old-database retention time are acknowledged;
- an observation period completes without database or queue regressions.

Neon's provider-specific procedure is documented in its
[DigitalOcean migration guide](https://neon.com/docs/import/migrate-from-digital-ocean).
