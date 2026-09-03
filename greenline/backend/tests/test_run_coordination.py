"""Behavioral contracts for durable Run Jobs and their worker."""

from __future__ import annotations

import os
import threading
from typing import Any
from uuid import uuid4

import pytest

import learner_state
import run_coordination


class _OneJobAdapter:
    def __init__(self) -> None:
        self.finished = threading.Event()
        self.output = ""
        self.result: dict[str, Any] | None = None
        self.failed: str | None = None
        self._claimed = False

    def enqueue(self, request):  # pragma: no cover - worker does not enqueue
        raise NotImplementedError

    def claim(self, worker_id: str):
        if self._claimed:
            return None
        self._claimed = True
        return run_coordination.RunJobClaim(
            job_id=uuid4(),
            user_id="learner-a",
            slug="demo",
            session_elapsed_ms=1200,
            workspace_revision=7,
            fence=4,
            claim_token=uuid4(),
            worker_id=worker_id,
        )

    def heartbeat(self, claim) -> None:
        return None

    def append_output(self, claim, chunk: str) -> None:
        self.output += chunk

    def complete(self, claim, completion) -> None:
        self.result = dict(completion.result)
        self.finished.set()

    def fail(self, claim, public_error: str) -> None:
        self.failed = public_error
        self.finished.set()

    def get(self, job_id, *, after=0, user_id=None):  # pragma: no cover
        raise NotImplementedError


class _SnapshotState:
    def snapshot(self, slug: str, user_id: str | None):
        return learner_state.WorkspaceSnapshot(
            revision=7,
            files={"answer.py": "answer = 42\n"},
        )


class _RecordingExecution:
    def __init__(self) -> None:
        self.workspace = None

    def execute(self, request, on_output=None):
        self.workspace = request.workspace
        if on_output is not None:
            on_output("one test passed\n")
        return {
            "green": True,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "exit_code": 0,
            "output": "one test passed\n",
            "tests": [],
        }


def test_worker_executes_the_enqueued_snapshot_and_publishes_the_result() -> None:
    jobs = _OneJobAdapter()
    execution = _RecordingExecution()
    worker = run_coordination.RunJobWorker(
        jobs,
        _SnapshotState(),
        execution,
        workers=1,
        poll_interval=0.01,
    )

    worker.start()
    try:
        assert jobs.finished.wait(timeout=2)
    finally:
        worker.stop()

    assert execution.workspace == {"answer.py": "answer = 42\n"}
    assert jobs.output == "one test passed\n"
    assert jobs.result is not None and jobs.result["green"] is True
    assert jobs.failed is None


@pytest.mark.skipif(
    not os.environ.get("GREENLINE_TEST_DATABASE_URL"),
    reason="requires a schema-version-3 PostgreSQL integration database",
)
def test_postgres_run_jobs_are_tenant_scoped_and_release_the_operation_lease() -> None:
    dsn = os.environ["GREENLINE_TEST_DATABASE_URL"]
    producer = run_coordination.PostgresRunJobAdapter.connect(dsn)
    consumer = run_coordination.PostgresRunJobAdapter.connect(dsn)
    state = learner_state.PostgresLearnerStateAdapter.connect(dsn)
    user_id = f"run-job-contract-{uuid4().hex}"
    slug = "job-lease"
    try:
        queued = producer.enqueue(
            run_coordination.RunJobRequest(
                user_id=user_id,
                slug=slug,
                session_elapsed_ms=1200,
            )
        )
        with pytest.raises(learner_state.LearnerChallengeBusy):
            consumer.enqueue(run_coordination.RunJobRequest(user_id=user_id, slug=slug))

        claim = consumer.claim("contract-worker")
        assert claim is not None
        consumer.append_output(claim, "one test passed\n")
        consumer.complete(
            claim,
            run_coordination.RunCompletion(
                started_at="2026-09-02T12:00:00+00:00",
                duration_ms=45,
                result={
                    "green": True,
                    "passed": 1,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "exit_code": 0,
                    "output": "one test passed\n",
                    "tests": [],
                },
            ),
        )

        completed = producer.get(queued["job_id"], user_id=user_id)
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["result"]["run"]["session_elapsed_ms"] == 1200
        assert producer.get(queued["job_id"], user_id="another-user") is None
        assert state.get_all(user_id)[slug]["status"] == "solved"

        next_job = producer.enqueue(
            run_coordination.RunJobRequest(user_id=user_id, slug=slug)
        )
        next_claim = consumer.claim("cleanup-worker")
        assert next_claim is not None and next_claim.job_id.hex == next_job["job_id"]
        consumer.fail(next_claim, "contract cleanup")
        state.reset(slug, user_id)
    finally:
        producer.close()
        consumer.close()
        state.close()


@pytest.mark.skipif(
    not os.environ.get("GREENLINE_TEST_DATABASE_URL"),
    reason="requires a schema-version-3 PostgreSQL integration database",
)
def test_postgres_run_admission_enforces_per_user_capacity_across_challenges() -> None:
    dsn = os.environ["GREENLINE_TEST_DATABASE_URL"]
    adapter = run_coordination.PostgresRunJobAdapter.connect(
        dsn,
        run_coordination.RunAdmissionPolicy(
            max_active_runs=2,
            max_active_runs_per_user=1,
        ),
    )
    state = learner_state.PostgresLearnerStateAdapter.connect(dsn)
    user_id = f"run-capacity-contract-{uuid4().hex}"
    try:
        first = adapter.enqueue(
            run_coordination.RunJobRequest(user_id=user_id, slug="job-lease")
        )
        with pytest.raises(run_coordination.RunCapacityExceeded):
            adapter.enqueue(
                run_coordination.RunJobRequest(user_id=user_id, slug="queue-drain")
            )

        claim = adapter.claim("capacity-cleanup-worker")
        assert claim is not None and claim.job_id.hex == first["job_id"]
        adapter.fail(claim, "contract cleanup")
        state.reset("job-lease", user_id)
    finally:
        adapter.close()
        state.close()
