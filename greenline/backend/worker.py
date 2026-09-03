"""Supported Hosted Mode execution-worker process.

The public API never imports this module and therefore never receives Docker
execution authority. This process has no HTTP listener or authentication
credentials; it only claims durable Run Jobs and executes their snapshots.
"""

from __future__ import annotations

import os
import signal
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

import abuse_controls
import learner_state
import operations
import run_coordination
import runner


@dataclass(frozen=True)
class WorkerViolation:
    code: str
    message: str


class WorkerConfigurationError(RuntimeError):
    def __init__(self, violations: list[WorkerViolation]) -> None:
        self.violations = tuple(violations)
        super().__init__("; ".join(item.message for item in violations))


@dataclass(frozen=True)
class WorkerAdapters:
    execution: runner.ContainerExecutionAdapter | None = None
    learner_state: learner_state.PostgresLearnerStateAdapter | None = None
    run_jobs: run_coordination.PostgresRunJobAdapter | None = None


@dataclass(frozen=True)
class WorkerRuntime:
    execution: runner.ContainerExecutionAdapter
    learner_state: learner_state.PostgresLearnerStateAdapter
    run_jobs: run_coordination.PostgresRunJobAdapter
    workers: int
    security_events: operations.SecurityEventSink
    release_sha: str

    def close(self) -> None:
        self.run_jobs.close()
        self.learner_state.close()


def _container_adapter(source: Mapping[str, str]) -> runner.ContainerExecutionAdapter:
    python_image = source.get("GREENLINE_PYTHON_EXECUTION_IMAGE", "").strip()
    node_image = source.get("GREENLINE_NODE_EXECUTION_IMAGE", "").strip()
    bundle_root = source.get("GREENLINE_RUN_BUNDLE_DIR", "").strip()
    if not python_image or not node_image or not bundle_root:
        raise runner.ContainerExecutionConfigurationError(
            "both execution images and shared Run Bundle storage are required"
        )
    return runner.ContainerExecutionAdapter(
        runner.ContainerExecutionPolicy(
            python_image=python_image,
            node_image=node_image,
            bundle_root=bundle_root,
            docker_binary=source.get("GREENLINE_DOCKER_BINARY", "docker").strip()
            or "docker",
        )
    )


def compose_worker(
    environment: Mapping[str, str] | None = None,
    *,
    adapters: WorkerAdapters | None = None,
) -> WorkerRuntime:
    """Compose every privileged dependency and fail before claiming work."""
    source = os.environ if environment is None else environment
    supplied = adapters or WorkerAdapters()
    violations: list[WorkerViolation] = []
    owns_state = False
    owns_jobs = False

    if source.get("GREENLINE_MODE") != "hosted":
        violations.append(
            WorkerViolation("hosted_mode_required", "worker requires Hosted Mode")
        )
    if source.get("GREENLINE_PROCESS_ROLE") != "worker":
        violations.append(
            WorkerViolation("worker_process_role_required", "worker role is required")
        )
    release_sha = source.get("GREENLINE_RELEASE_SHA", "").strip()
    if len(release_sha) != 40 or any(
        character not in "0123456789abcdef" for character in release_sha
    ):
        violations.append(
            WorkerViolation(
                "release_identity_required",
                "worker requires GREENLINE_RELEASE_SHA as a full lowercase commit SHA",
            )
        )

    try:
        database_url = operations.read_secret(source, "GREENLINE_DATABASE_URL")
        log_hmac_key = operations.read_secret(source, "GREENLINE_LOG_HMAC_KEY")
    except operations.OperationalConfigurationError:
        database_url = None
        log_hmac_key = None
        violations.append(
            WorkerViolation(
                "invalid_secret_configuration",
                "worker secrets must use one valid direct or absolute file source",
            )
        )

    try:
        policy = abuse_controls.policy_from_environment(source)
    except (TypeError, ValueError):
        policy = abuse_controls.AbuseControlPolicy()
        violations.append(
            WorkerViolation(
                "invalid_abuse_configuration",
                "worker Run Job limits must be positive and internally consistent",
            )
        )

    try:
        workers = int(source.get("GREENLINE_WORKER_CONCURRENCY", "4"))
        if not 1 <= workers <= 32:
            raise ValueError
    except ValueError:
        workers = 4
        violations.append(
            WorkerViolation(
                "invalid_worker_concurrency",
                "GREENLINE_WORKER_CONCURRENCY must be between 1 and 32",
            )
        )

    execution = supplied.execution
    if type(execution) is not runner.ContainerExecutionAdapter:
        try:
            execution = _container_adapter(source)
        except runner.ContainerExecutionConfigurationError:
            execution = None
            violations.append(
                WorkerViolation(
                    "isolated_execution_required",
                    "worker requires both digest-pinned execution images",
                )
            )
    if execution is not None:
        try:
            execution.check_ready()
        except runner.ExecutionUnavailable:
            violations.append(
                WorkerViolation(
                    "isolated_execution_unavailable",
                    "worker container runtime or immutable images are unavailable",
                )
            )

    state = supplied.learner_state
    if type(state) is not learner_state.PostgresLearnerStateAdapter:
        if database_url:
            try:
                state = learner_state.PostgresLearnerStateAdapter.connect(database_url)
                owns_state = True
            except learner_state.LearnerStateUnavailable:
                state = None
        if state is None:
            violations.append(
                WorkerViolation(
                    "durable_state_required",
                    "worker requires PostgreSQL learner state",
                )
            )
    if state is not None:
        try:
            state.check_ready()
        except learner_state.LearnerStateUnavailable:
            violations.append(
                WorkerViolation(
                    "durable_state_unavailable",
                    "worker PostgreSQL learner state is unavailable",
                )
            )

    jobs = supplied.run_jobs
    admission = run_coordination.RunAdmissionPolicy(
        max_active_runs=policy.max_active_runs,
        max_active_runs_per_user=policy.max_active_runs_per_user,
    )
    if type(jobs) is not run_coordination.PostgresRunJobAdapter:
        if database_url:
            try:
                jobs = run_coordination.PostgresRunJobAdapter.connect(
                    database_url, admission
                )
                owns_jobs = True
            except run_coordination.RunJobsUnavailable:
                jobs = None
        if jobs is None:
            violations.append(
                WorkerViolation(
                    "distributed_coordination_required",
                    "worker requires durable Run Jobs",
                )
            )
    if jobs is not None:
        try:
            jobs.check_ready()
        except run_coordination.RunJobsUnavailable:
            violations.append(
                WorkerViolation(
                    "distributed_coordination_unavailable",
                    "worker durable Run Jobs are unavailable",
                )
            )
        if jobs.admission_policy != admission:
            violations.append(
                WorkerViolation(
                    "invalid_abuse_configuration",
                    "worker Run Job limits must match the API admission policy",
                )
            )

    security_events: operations.SecurityEventSink = operations.NullSecurityEventSink()
    if log_hmac_key is None:
        violations.append(
            WorkerViolation(
                "security_logging_required",
                "worker requires GREENLINE_LOG_HMAC_KEY or its file source",
            )
        )
    else:
        try:
            security_events = operations.JsonSecurityEventSink(
                log_hmac_key.encode("utf-8")
            )
        except operations.OperationalConfigurationError:
            violations.append(
                WorkerViolation(
                    "invalid_security_logging_configuration",
                    "worker security-log HMAC key must contain at least 32 bytes",
                )
            )

    if violations:
        if owns_jobs and jobs is not None:
            jobs.close()
        if owns_state and state is not None:
            state.close()
        raise WorkerConfigurationError(violations)
    assert execution is not None and state is not None and jobs is not None
    return WorkerRuntime(execution, state, jobs, workers, security_events, release_sha)


def _report_release_until_stopped(
    runtime: WorkerRuntime,
    worker_id: str,
    stop: threading.Event,
) -> None:
    """Refresh readiness only after the complete execution runtime is rechecked."""
    while not stop.is_set():
        try:
            runtime.execution.check_ready()
            runtime.run_jobs.report_worker_release(
                worker_id,
                runtime.release_sha,
                runtime.execution.policy.python_image,
                runtime.execution.policy.node_image,
            )
        except (runner.ExecutionUnavailable, run_coordination.RunJobsUnavailable):
            pass
        stop.wait(run_coordination.WORKER_RELEASE_MAX_AGE_SECONDS / 3)


def main() -> None:
    os.environ["GREENLINE_PROCESS_ROLE"] = "worker"
    runtime = compose_worker()
    stop = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker = run_coordination.RunJobWorker(
        runtime.run_jobs,
        runtime.learner_state,
        runtime.execution,
        workers=runtime.workers,
    )
    release_thread = threading.Thread(
        target=_report_release_until_stopped,
        args=(runtime, f"worker-{uuid4().hex}", stop),
        name="worker-release-heartbeat",
        daemon=True,
    )
    try:
        release_thread.start()
        worker.start()
        runtime.security_events.emit(
            "worker.started", fields={"concurrency": runtime.workers}
        )
        stop.wait()
    finally:
        stop.set()
        release_thread.join(timeout=1)
        worker.stop(join_timeout=75)
        runtime.close()
        runtime.security_events.emit("worker.stopped")


if __name__ == "__main__":
    main()
