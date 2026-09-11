"""Behavioral contracts for durable Run Jobs and their worker."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
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


class _ManyJobsAdapter:
    def __init__(self, users: int) -> None:
        self._lock = threading.Lock()
        self._claims = deque(
            run_coordination.RunJobClaim(
                job_id=uuid4(),
                user_id=f"learner-{index}",
                slug="demo",
                session_elapsed_ms=None,
                workspace_revision=7,
                fence=1,
                claim_token=uuid4(),
                worker_id="",
            )
            for index in range(users)
        )
        self.completed = 0
        self.failed = 0
        self.finished = threading.Event()
        self._expected = users

    def claim(self, worker_id: str):
        with self._lock:
            if not self._claims:
                return None
            claim = self._claims.popleft()
        return run_coordination.RunJobClaim(
            **{
                **vars(claim),
                "worker_id": worker_id,
            }
        )

    def heartbeat(self, claim) -> None:
        return None

    def append_output(self, claim, chunk: str) -> None:
        return None

    def complete(self, claim, completion) -> None:
        with self._lock:
            self.completed += 1
            if self.completed + self.failed == self._expected:
                self.finished.set()

    def fail(self, claim, public_error: str) -> None:
        with self._lock:
            self.failed += 1
            if self.completed + self.failed == self._expected:
                self.finished.set()


class _ConcurrencyRecordingExecution:
    def __init__(self, expected_concurrency: int) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self._expected_concurrency = expected_concurrency
        self._first_wave_ready = threading.Event()

    def execute(self, request, on_output=None):
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            if self._active == self._expected_concurrency:
                self._first_wave_ready.set()
        assert self._first_wave_ready.wait(timeout=1)
        time.sleep(0.002)
        with self._lock:
            self._active -= 1
        return {
            "green": True,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "exit_code": 0,
            "output": "",
            "tests": [],
        }


@pytest.mark.parametrize("active_users", [15, 50, 100])
def test_worker_pool_serves_distinct_active_users_concurrently(
    active_users: int,
) -> None:
    workers = 4
    jobs = _ManyJobsAdapter(active_users)
    execution = _ConcurrencyRecordingExecution(workers)
    worker = run_coordination.RunJobWorker(
        jobs,
        _SnapshotState(),
        execution,
        workers=workers,
        poll_interval=0.001,
    )

    worker.start()
    try:
        assert jobs.finished.wait(timeout=5)
    finally:
        worker.stop()

    assert jobs.completed == active_users
    assert jobs.failed == 0
    assert execution.max_active == workers


class _ReleaseRowsCursor:
    def __init__(self, rows) -> None:
        self._rows = rows

    def fetchall(self):
        return self._rows


class _ReleaseRowsConnection:
    def __init__(self, rows) -> None:
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, _query, _args):
        return _ReleaseRowsCursor(self._rows)


class _ReleaseRowsPool:
    def __init__(self, rows) -> None:
        self._rows = rows

    def connection(self):
        return _ReleaseRowsConnection(self._rows)


def test_release_status_rejects_mixed_or_inconsistent_live_workers() -> None:
    source_sha = "a" * 40
    python_image = "greenline-python@sha256:" + "b" * 64
    node_image = "greenline-node@sha256:" + "c" * 64
    matching = {
        "source_sha": source_sha,
        "python_execution_image": python_image,
        "node_execution_image": node_image,
    }
    mixed_release = {
        **matching,
        "source_sha": "d" * 40,
    }
    mixed_images = {
        **matching,
        "node_execution_image": "greenline-node@sha256:" + "e" * 64,
    }

    healthy = run_coordination.PostgresRunJobAdapter(
        _ReleaseRowsPool([matching, matching])
    ).worker_release_status(source_sha)
    wrong_release = run_coordination.PostgresRunJobAdapter(
        _ReleaseRowsPool([matching, mixed_release])
    ).worker_release_status(source_sha)
    inconsistent_images = run_coordination.PostgresRunJobAdapter(
        _ReleaseRowsPool([matching, mixed_images])
    ).worker_release_status(source_sha)

    assert healthy.ready is True
    assert healthy.live_workers == healthy.matching_workers == 2
    assert healthy.python_execution_image == python_image
    assert wrong_release.ready is False
    assert inconsistent_images.ready is False


@pytest.mark.skipif(
    not os.environ.get("GREENLINE_TEST_DATABASE_URL"),
    reason="requires a schema-version-7 PostgreSQL integration database",
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
                workspace={"answer.py": "answer = 42\n"},
            ),
        )

        completed = producer.get(queued["job_id"], user_id=user_id)
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["result"]["run"]["session_elapsed_ms"] == 1200
        assert state.list_runs(slug, 10, user_id)[0]["snapshot_available"] is True
        assert producer.get(queued["job_id"], user_id="another-user") is None
        assert state.get_all(user_id)[slug]["status"] == "solved"
        event_names = [
            event["event_name"] for event in state.list_product_events(user_id)
        ]
        assert event_names.count("first_run") == 1
        assert event_names.count("successful_run") == 1

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
    reason="requires a schema-version-7 PostgreSQL integration database",
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
