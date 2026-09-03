from __future__ import annotations

from pathlib import Path

import pytest

from learner_state import PostgresLearnerStateAdapter
from run_coordination import PostgresRunJobAdapter
import runner
from worker import (
    WorkerAdapters,
    WorkerConfigurationError,
    compose_worker,
)


IMAGE_DIGEST = "sha256:" + "a" * 64


class _ReadyCursor:
    def fetchone(self) -> dict[str, int]:
        return {"version": 3}


class _ReadyConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, _query: str) -> _ReadyCursor:
        return _ReadyCursor()


class _ReadyPool:
    def connection(self, **_kwargs) -> _ReadyConnection:
        return _ReadyConnection()

    def close(self) -> None:
        return None


def _codes(error: WorkerConfigurationError) -> set[str]:
    return {item.code for item in error.violations}


def _environment(**values: str) -> dict[str, str]:
    return {
        "GREENLINE_MODE": "hosted",
        "GREENLINE_PROCESS_ROLE": "worker",
        "GREENLINE_LOG_HMAC_KEY": "test-worker-key-" + "x" * 32,
        "GREENLINE_RELEASE_SHA": "a" * 40,
        **values,
    }


def _container(fake_docker: Path, bundle_root: Path) -> runner.ContainerExecutionAdapter:
    return runner.ContainerExecutionAdapter(
        runner.ContainerExecutionPolicy(
            python_image=f"greenline-python@{IMAGE_DIGEST}",
            node_image=f"greenline-node@{IMAGE_DIGEST}",
            bundle_root=str(bundle_root),
            docker_binary=str(fake_docker),
        )
    )


def _ready_docker(tmp_path: Path) -> Path:
    executable = tmp_path / "docker"
    executable.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = version ]; then echo 29.0.0; exit 0; fi\n"
        "if [ \"$1 $2\" = 'image inspect' ]; then echo sha256:one; echo sha256:two; exit 0; fi\n"
        "if [ \"$1\" = create ]; then echo readiness-container; exit 0; fi\n"
        "if [ \"$1\" = rm ]; then exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def test_worker_refuses_to_start_without_privileged_dependencies() -> None:
    with pytest.raises(WorkerConfigurationError) as raised:
        compose_worker({})

    assert _codes(raised.value) == {
        "hosted_mode_required",
        "worker_process_role_required",
        "isolated_execution_required",
        "durable_state_required",
        "distributed_coordination_required",
        "security_logging_required",
        "release_identity_required",
    }


def test_worker_composes_only_with_ready_container_and_durable_adapters(
    tmp_path: Path,
) -> None:
    runtime = compose_worker(
        _environment(GREENLINE_WORKER_CONCURRENCY="3"),
        adapters=WorkerAdapters(
            execution=_container(_ready_docker(tmp_path), tmp_path),
            learner_state=PostgresLearnerStateAdapter(pool=_ReadyPool()),
            run_jobs=PostgresRunJobAdapter(pool=_ReadyPool()),
        ),
    )

    assert runtime.workers == 3
    assert type(runtime.execution) is runner.ContainerExecutionAdapter
    runtime.close()


def test_worker_refuses_an_unavailable_execution_runtime(tmp_path: Path) -> None:
    missing = tmp_path / "missing-docker"
    with pytest.raises(WorkerConfigurationError) as raised:
        compose_worker(
            _environment(),
            adapters=WorkerAdapters(
                execution=_container(missing, tmp_path),
                learner_state=PostgresLearnerStateAdapter(pool=_ReadyPool()),
                run_jobs=PostgresRunJobAdapter(pool=_ReadyPool()),
            ),
        )

    assert "isolated_execution_unavailable" in _codes(raised.value)


@pytest.mark.parametrize("concurrency", ["0", "33", "many"])
def test_worker_concurrency_is_bounded(concurrency: str) -> None:
    with pytest.raises(WorkerConfigurationError) as raised:
        compose_worker(_environment(GREENLINE_WORKER_CONCURRENCY=concurrency))

    assert "invalid_worker_concurrency" in _codes(raised.value)
