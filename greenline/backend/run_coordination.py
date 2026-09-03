"""Durable Run Job queue, fenced claims, and disposable worker machinery."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID, uuid4

import learner_state
import progress
import runner


OUTPUT_LIMIT = 20_000
CLAIM_SECONDS = 30
QUEUE_LEASE_SECONDS = 90
MAX_CLAIM_ATTEMPTS = 3
TERMINAL_RETENTION_SECONDS = 3600


class RunJobsUnavailable(RuntimeError):
    """The durable Run Job dependency is unavailable."""


class StaleRunJobClaim(RuntimeError):
    """A recovered or superseded worker no longer owns this Run Job."""


class RunCapacityExceeded(RuntimeError):
    """The configured global or learner Run Job capacity is exhausted."""

    retry_after = 5


@dataclass(frozen=True)
class RunAdmissionPolicy:
    max_active_runs: int = 20
    max_active_runs_per_user: int = 2

    def __post_init__(self) -> None:
        if self.max_active_runs < 1 or self.max_active_runs_per_user < 1:
            raise ValueError("active Run Job limits must be positive")
        if self.max_active_runs_per_user > self.max_active_runs:
            raise ValueError(
                "max_active_runs_per_user cannot exceed max_active_runs"
            )


@dataclass(frozen=True)
class RunJobRequest:
    user_id: str
    slug: str
    session_elapsed_ms: int | None = None


@dataclass(frozen=True)
class RunJobClaim:
    job_id: UUID
    user_id: str
    slug: str
    session_elapsed_ms: int | None
    workspace_revision: int
    fence: int
    claim_token: UUID
    worker_id: str


@dataclass(frozen=True)
class RunCompletion:
    started_at: str
    duration_ms: int
    result: Mapping[str, Any]


class RunJobAdapter(Protocol):
    def check_ready(self) -> None: ...

    def enqueue(self, request: RunJobRequest) -> dict[str, Any]: ...
    def claim(self, worker_id: str) -> RunJobClaim | None: ...
    def heartbeat(self, claim: RunJobClaim) -> None: ...
    def append_output(self, claim: RunJobClaim, chunk: str) -> None: ...
    def complete(self, claim: RunJobClaim, completion: RunCompletion) -> None: ...
    def fail(self, claim: RunJobClaim, public_error: str) -> None: ...
    def get(
        self, job_id: str, *, after: int = 0, user_id: str | None = None
    ) -> dict[str, Any] | None: ...


class PostgresRunJobAdapter:
    """Persist and fence Run Jobs across processes and replicas."""

    _ADMISSION_LOCK = 3_847_562_019

    def __init__(
        self,
        pool: Any,
        admission_policy: RunAdmissionPolicy | None = None,
    ) -> None:
        self._pool = pool
        self.admission_policy = admission_policy or RunAdmissionPolicy()

    @classmethod
    def connect(
        cls,
        dsn: str,
        admission_policy: RunAdmissionPolicy | None = None,
    ) -> "PostgresRunJobAdapter":
        pool = None
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=10,
                open=True,
                kwargs={"row_factory": dict_row},
            )
            adapter = cls(pool, admission_policy)
            adapter.check_ready()
            return adapter
        except Exception as exc:
            if pool is not None:
                pool.close()
            raise RunJobsUnavailable("durable Run Jobs are unavailable") from exc

    def close(self) -> None:
        self._pool.close()

    def check_ready(self) -> None:
        try:
            with self._pool.connection(timeout=3) as conn:
                row = conn.execute(
                    "SELECT version FROM greenline_schema_version WHERE singleton = TRUE"
                ).fetchone()
        except Exception as exc:
            raise RunJobsUnavailable("durable Run Jobs are unavailable") from exc
        if row is None or row["version"] != learner_state.SCHEMA_VERSION:
            raise RunJobsUnavailable("Run Job schema migration is required")

    @contextmanager
    def _connection(self):
        try:
            with self._pool.connection() as conn:
                yield conn
        except (
            learner_state.LearnerChallengeBusy,
            learner_state.LearnerIdentityRequired,
            RunCapacityExceeded,
            StaleRunJobClaim,
            RunJobsUnavailable,
        ):
            raise
        except Exception as exc:
            raise RunJobsUnavailable("durable Run Jobs are unavailable") from exc

    @staticmethod
    def _ensure_state(conn: Any, user_id: str, slug: str) -> None:
        conn.execute(
            "INSERT INTO learner_challenges (user_id, slug) VALUES (%s, %s) "
            "ON CONFLICT (user_id, slug) DO NOTHING",
            (user_id, slug),
        )

    @staticmethod
    def _retire_expired(conn: Any, job_id: UUID) -> None:
        conn.execute(
            "UPDATE run_jobs SET status = 'failed', error = 'operation lease expired', "
            "completed_at = now(), terminal_expires_at = now() + "
            "(%s * interval '1 second') WHERE id = %s "
            "AND status IN ('queued', 'running')",
            (TERMINAL_RETENTION_SECONDS, job_id),
        )

    @staticmethod
    def _prune_terminal(conn: Any) -> None:
        conn.execute(
            "DELETE FROM run_jobs WHERE id IN (SELECT id FROM run_jobs "
            "WHERE terminal_expires_at <= now() ORDER BY terminal_expires_at LIMIT 100)"
        )

    def _admit_run(self, conn: Any, user_id: str) -> None:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (self._ADMISSION_LOCK,))
        row = conn.execute(
            "SELECT count(*) AS global_active, "
            "count(*) FILTER (WHERE user_id = %s) AS user_active "
            "FROM run_jobs WHERE status IN ('queued', 'running')",
            (user_id,),
        ).fetchone()
        if (
            row["global_active"] >= self.admission_policy.max_active_runs
            or row["user_active"] >= self.admission_policy.max_active_runs_per_user
        ):
            raise RunCapacityExceeded("Run Job capacity exceeded")

    def enqueue(self, request: RunJobRequest) -> dict[str, Any]:
        if not request.user_id:
            raise learner_state.LearnerIdentityRequired(
                "verified learner identity is required"
            )
        job_id = uuid4()
        with self._connection() as conn:
            self._admit_run(conn, request.user_id)
            self._ensure_state(conn, request.user_id, request.slug)
            state = conn.execute(
                "SELECT workspace_revision, operation_fence, lease_job_id, "
                "lease_expires_at > now() AS lease_live FROM learner_challenges "
                "WHERE user_id = %s AND slug = %s FOR UPDATE",
                (request.user_id, request.slug),
            ).fetchone()
            if state["lease_job_id"] is not None and state["lease_live"]:
                raise learner_state.LearnerChallengeBusy(
                    "challenge operation already in progress"
                )
            if state["lease_job_id"] is not None:
                self._retire_expired(conn, state["lease_job_id"])
            fence = state["operation_fence"] + 1
            conn.execute(
                "INSERT INTO run_jobs (id, user_id, slug, session_elapsed_ms, "
                "workspace_revision, status, fence) "
                "VALUES (%s, %s, %s, %s, %s, 'queued', %s)",
                (
                    job_id,
                    request.user_id,
                    request.slug,
                    request.session_elapsed_ms,
                    state["workspace_revision"],
                    fence,
                ),
            )
            conn.execute(
                "UPDATE learner_challenges SET operation_fence = %s, lease_job_id = %s, "
                "lease_expires_at = now() + (%s * interval '1 second'), "
                "updated_at = now() WHERE user_id = %s AND slug = %s",
                (
                    fence,
                    job_id,
                    QUEUE_LEASE_SECONDS,
                    request.user_id,
                    request.slug,
                ),
            )
        return {"job_id": job_id.hex, "slug": request.slug, "status": "queued"}

    def claim(self, worker_id: str) -> RunJobClaim | None:
        with self._connection() as conn:
            self._prune_terminal(conn)
            row = conn.execute(
                "SELECT jobs.id, jobs.user_id, jobs.slug, jobs.session_elapsed_ms, "
                "jobs.workspace_revision, jobs.fence, jobs.claim_attempts "
                "FROM run_jobs AS jobs JOIN learner_challenges AS state "
                "ON state.user_id = jobs.user_id AND state.slug = jobs.slug "
                "WHERE (jobs.status = 'queued' OR "
                "(jobs.status = 'running' AND jobs.claim_expires_at <= now())) "
                "AND state.lease_job_id = jobs.id "
                "AND state.operation_fence = jobs.fence "
                "ORDER BY jobs.created_at LIMIT 1 FOR UPDATE OF state, jobs SKIP LOCKED"
            ).fetchone()
            if row is None:
                return None
            if row["claim_attempts"] >= MAX_CLAIM_ATTEMPTS:
                self._retire_expired(conn, row["id"])
                conn.execute(
                    "UPDATE learner_challenges SET lease_job_id = NULL, "
                    "lease_expires_at = NULL WHERE user_id = %s AND slug = %s "
                    "AND lease_job_id = %s AND operation_fence = %s",
                    (row["user_id"], row["slug"], row["id"], row["fence"]),
                )
                return None
            claim_token = uuid4()
            conn.execute(
                "UPDATE run_jobs SET status = 'running', claim_token = %s, worker_id = %s, "
                "claim_expires_at = now() + (%s * interval '1 second'), "
                "claim_attempts = claim_attempts + 1, claimed_at = COALESCE(claimed_at, now()), "
                "heartbeat_at = now() WHERE id = %s",
                (claim_token, worker_id, CLAIM_SECONDS, row["id"]),
            )
            conn.execute(
                "UPDATE learner_challenges SET lease_expires_at = now() + "
                "(%s * interval '1 second') WHERE user_id = %s AND slug = %s",
                (QUEUE_LEASE_SECONDS, row["user_id"], row["slug"]),
            )
        return RunJobClaim(
            job_id=row["id"],
            user_id=row["user_id"],
            slug=row["slug"],
            session_elapsed_ms=row["session_elapsed_ms"],
            workspace_revision=row["workspace_revision"],
            fence=row["fence"],
            claim_token=claim_token,
            worker_id=worker_id,
        )

    @staticmethod
    def _claim_where(claim: RunJobClaim) -> tuple[Any, ...]:
        return (
            claim.job_id,
            claim.fence,
            claim.claim_token,
            claim.worker_id,
        )

    def heartbeat(self, claim: RunJobClaim) -> None:
        with self._connection() as conn:
            job = conn.execute(
                "UPDATE run_jobs SET heartbeat_at = now(), claim_expires_at = now() + "
                "(%s * interval '1 second') WHERE id = %s AND fence = %s "
                "AND claim_token = %s AND worker_id = %s AND status = 'running' RETURNING id",
                (CLAIM_SECONDS, *self._claim_where(claim)),
            ).fetchone()
            state = conn.execute(
                "UPDATE learner_challenges SET lease_expires_at = now() + "
                "(%s * interval '1 second') WHERE user_id = %s AND slug = %s "
                "AND lease_job_id = %s AND operation_fence = %s RETURNING slug",
                (
                    QUEUE_LEASE_SECONDS,
                    claim.user_id,
                    claim.slug,
                    claim.job_id,
                    claim.fence,
                ),
            ).fetchone()
            if job is None or state is None:
                raise StaleRunJobClaim("Run Job claim is stale")

    def append_output(self, claim: RunJobClaim, chunk: str) -> None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT output, output_base FROM run_jobs WHERE id = %s AND fence = %s "
                "AND claim_token = %s AND worker_id = %s AND status = 'running' FOR UPDATE",
                self._claim_where(claim),
            ).fetchone()
            if row is None:
                raise StaleRunJobClaim("Run Job claim is stale")
            combined = row["output"] + chunk
            dropped = max(0, len(combined) - OUTPUT_LIMIT)
            conn.execute(
                "UPDATE run_jobs SET output = %s, output_base = %s WHERE id = %s",
                (combined[dropped:], row["output_base"] + dropped, claim.job_id),
            )

    def _locked_claim(self, conn: Any, claim: RunJobClaim) -> Mapping[str, Any]:
        row = conn.execute(
            "SELECT jobs.session_elapsed_ms FROM run_jobs AS jobs "
            "JOIN learner_challenges AS state ON state.user_id = jobs.user_id "
            "AND state.slug = jobs.slug WHERE jobs.id = %s AND jobs.fence = %s "
            "AND jobs.claim_token = %s AND jobs.worker_id = %s "
            "AND jobs.status = 'running' AND state.lease_job_id = jobs.id "
            "AND state.operation_fence = jobs.fence "
            "FOR UPDATE OF state, jobs",
            self._claim_where(claim),
        ).fetchone()
        if row is None:
            raise StaleRunJobClaim("Run Job claim is stale")
        return row

    def complete(self, claim: RunJobClaim, completion: RunCompletion) -> None:
        result = dict(completion.result)
        green = bool(result.get("green"))
        output = str(result.get("output", ""))
        history_tail = output[-progress.OUTPUT_TAIL_LIMIT :]
        with self._connection() as conn:
            job = self._locked_claim(conn, claim)
            state = conn.execute(
                "UPDATE learner_challenges SET attempts = attempts + 1, "
                "status = CASE WHEN status = 'solved' OR %s THEN 'solved' "
                "ELSE 'attempted' END, solved_at = CASE WHEN %s "
                "THEN COALESCE(solved_at, now()) ELSE solved_at END, "
                "lease_job_id = NULL, lease_expires_at = NULL, updated_at = now() "
                "WHERE user_id = %s AND slug = %s AND lease_job_id = %s "
                "AND operation_fence = %s RETURNING attempts, status, solved_at, spoiled",
                (
                    green,
                    green,
                    claim.user_id,
                    claim.slug,
                    claim.job_id,
                    claim.fence,
                ),
            ).fetchone()
            if state is None:
                raise StaleRunJobClaim("Run Job lease is stale")
            run = conn.execute(
                "INSERT INTO challenge_runs (user_id, slug, started_at, duration_ms, "
                "session_elapsed_ms, green, passed, failed, errors, skipped, exit_code, "
                "output_tail, output_truncated, tests) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                "RETURNING id",
                (
                    claim.user_id,
                    claim.slug,
                    completion.started_at,
                    completion.duration_ms,
                    job["session_elapsed_ms"],
                    green,
                    int(result.get("passed", 0)),
                    int(result.get("failed", 0)),
                    int(result.get("errors", 0)),
                    int(result.get("skipped", 0)),
                    int(result.get("exit_code", 0)),
                    history_tail,
                    bool(result.get("output_truncated"))
                    or len(output) > len(history_tail),
                    json.dumps(result.get("tests") or []),
                ),
            ).fetchone()
            run_meta = {
                "id": run["id"],
                "slug": claim.slug,
                "started_at": completion.started_at,
                "duration_ms": completion.duration_ms,
                "session_elapsed_ms": job["session_elapsed_ms"],
                "green": green,
                "passed": int(result.get("passed", 0)),
                "failed": int(result.get("failed", 0)),
                "errors": int(result.get("errors", 0)),
                "skipped": int(result.get("skipped", 0)),
                "exit_code": int(result.get("exit_code", 0)),
            }
            result["run"] = run_meta
            result["duration_ms"] = completion.duration_ms
            output_tail = output[-OUTPUT_LIMIT:]
            conn.execute(
                "UPDATE run_jobs SET status = 'completed', result = %s::jsonb, "
                "output = %s, output_base = GREATEST(output_base, %s), "
                "completed_at = now(), terminal_expires_at = now() + "
                "(%s * interval '1 second'), claim_expires_at = NULL "
                "WHERE id = %s",
                (
                    json.dumps(result),
                    output_tail,
                    max(0, len(output) - len(output_tail)),
                    TERMINAL_RETENTION_SECONDS,
                    claim.job_id,
                ),
            )

    def fail(self, claim: RunJobClaim, public_error: str) -> None:
        error = public_error[:500]
        with self._connection() as conn:
            self._locked_claim(conn, claim)
            conn.execute(
                "UPDATE run_jobs SET status = 'failed', error = %s, completed_at = now(), "
                "terminal_expires_at = now() + (%s * interval '1 second'), "
                "claim_expires_at = NULL WHERE id = %s",
                (error, TERMINAL_RETENTION_SECONDS, claim.job_id),
            )
            conn.execute(
                "UPDATE learner_challenges SET lease_job_id = NULL, "
                "lease_expires_at = NULL WHERE user_id = %s AND slug = %s "
                "AND lease_job_id = %s AND operation_fence = %s",
                (claim.user_id, claim.slug, claim.job_id, claim.fence),
            )

    def get(
        self, job_id: str, *, after: int = 0, user_id: str | None = None
    ) -> dict[str, Any] | None:
        if not user_id:
            return None
        try:
            parsed_id = UUID(job_id)
        except ValueError:
            return None
        with self._connection() as conn:
            row = conn.execute(
                "SELECT id, slug, status, output, output_base, result, error, "
                "terminal_expires_at > now() AS retained FROM run_jobs "
                "WHERE id = %s AND user_id = %s",
                (parsed_id, user_id),
            ).fetchone()
        if row is None or (row["status"] in {"completed", "failed"} and not row["retained"]):
            return None
        output = row["output"]
        base = row["output_base"]
        bounded_after = max(base, min(int(after), base + len(output)))
        response: dict[str, Any] = {
            "job_id": row["id"].hex,
            "slug": row["slug"],
            "status": row["status"],
            "output": output[bounded_after - base :],
            "next_offset": base + len(output),
            "output_truncated": base > 0,
        }
        if row["result"] is not None:
            response["result"] = row["result"]
        if row["error"]:
            response["error"] = row["error"]
        return response


class RunJobWorker:
    """Claim durable work; all authority remains in the Adapter's fence."""

    def __init__(
        self,
        jobs: RunJobAdapter,
        state: learner_state.LearnerStateAdapter,
        execution: runner.ExecutionAdapter,
        *,
        workers: int = 4,
        poll_interval: float = 0.25,
    ) -> None:
        self._jobs = jobs
        self._state = state
        self._execution = execution
        self._workers = workers
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for index in range(self._workers):
            thread = threading.Thread(
                target=self._loop,
                name=f"run-worker-{index}-{uuid4().hex[:8]}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self, *, join_timeout: float = 2) -> None:
        self._stop.set()
        deadline = time.monotonic() + join_timeout
        for thread in self._threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))

    def _loop(self) -> None:
        worker_id = threading.current_thread().name
        while not self._stop.is_set():
            try:
                claim = self._jobs.claim(worker_id)
            except Exception:
                self._stop.wait(self._poll_interval)
                continue
            if claim is None:
                self._stop.wait(self._poll_interval)
                continue
            self._execute(claim)

    def _execute(self, claim: RunJobClaim) -> None:
        heartbeat_stop = threading.Event()
        lost = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(CLAIM_SECONDS / 3):
                try:
                    self._jobs.heartbeat(claim)
                except (StaleRunJobClaim, RunJobsUnavailable):
                    lost.set()
                    return

        heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        heartbeat_thread.start()
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()

        def emit(chunk: str) -> None:
            if lost.is_set():
                return
            try:
                self._jobs.append_output(claim, chunk)
            except (StaleRunJobClaim, RunJobsUnavailable):
                lost.set()

        try:
            snapshot = self._state.snapshot(claim.slug, claim.user_id)
            if snapshot.revision != claim.workspace_revision:
                raise StaleRunJobClaim("workspace changed after enqueue")
            result = self._execution.execute(
                runner.ChallengeRun(
                    slug=claim.slug,
                    user_id=claim.user_id,
                    workspace=snapshot.files,
                ),
                on_output=emit,
            )
            if lost.is_set():
                return
            self._jobs.complete(
                claim,
                RunCompletion(
                    started_at=started_at,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    result=result,
                ),
            )
        except StaleRunJobClaim:
            return
        except Exception:
            try:
                self._jobs.fail(claim, "challenge execution failed")
            except (StaleRunJobClaim, RunJobsUnavailable):
                pass
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)
