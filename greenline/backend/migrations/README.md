# PostgreSQL migrations

Hosted Mode never creates or alters its schema while serving traffic. Apply
the numbered SQL migrations in order during deployment, using a role allowed
to perform DDL. The application role should only receive data access.

For a fresh database:

```bash
psql "$GREENLINE_DATABASE_URL" --set ON_ERROR_STOP=1 \
  --file backend/migrations/001_learner_state.sql
psql "$GREENLINE_DATABASE_URL" --set ON_ERROR_STOP=1 \
  --file backend/migrations/002_run_coordination.sql
psql "$GREENLINE_DATABASE_URL" --set ON_ERROR_STOP=1 \
  --file backend/migrations/003_abuse_controls.sql
psql "$GREENLINE_DATABASE_URL" --set ON_ERROR_STOP=1 \
  --file backend/migrations/004_worker_releases.sql
```

`PostgresLearnerStateAdapter.check_ready()` verifies the exact schema version
before the Adapter is admitted by application composition. PostgreSQL contract
tests use `GREENLINE_TEST_DATABASE_URL` and require an already migrated,
disposable integration database.

Migration 002 adds durable Run Jobs and fenced operation leases. API processes
and disposable workers use the same PostgreSQL schema; workers do not own any
authoritative in-memory job state.

Migration 003 adds fixed one-minute request-budget windows and durable audit
events. Audit rows default to 30-day retention and are pruned incrementally by
request admission; set the retention explicitly for your operational policy.

Migration 004 adds short-lived worker release attestations. Workers refresh
their row only after rechecking Docker and both configured execution images;
the control plane uses the rows for listener-free exact-release readiness.
