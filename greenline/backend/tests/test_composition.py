from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from abuse_controls import PostgresAbuseControlAdapter
from app import CompositionError, HostedAdapters, create_application
from learner_state import PostgresLearnerStateAdapter
from run_coordination import PostgresRunJobAdapter
from runner import DisabledExecutionAdapter
OPERATIONS = {
    "GREENLINE_TRUSTED_PROXY_CIDRS": "10.0.0.0/8,127.0.0.1/32",
    "GREENLINE_PROXY_HEADERS_CONFIGURED": "1",
    "GREENLINE_PROCESS_ROLE": "api",
    "GREENLINE_LOG_HMAC_KEY": "test-log-key-" + "x" * 32,
    "GREENLINE_RELEASE_SHA": "a" * 40,
}


def _hosted_environment(**values: str) -> dict[str, str]:
    return {"GREENLINE_MODE": "hosted", **OPERATIONS, **values}


class _ReadyCursor:
    def __init__(self, query: str) -> None:
        self.query = query

    def fetchone(self) -> dict[str, int]:
        return {"version": 5}

    def fetchall(self) -> list[dict[str, str]]:
        if "FROM worker_releases" not in self.query:
            return []
        return [
            {
                "source_sha": "a" * 40,
                "python_execution_image": "greenline-python@sha256:" + "b" * 64,
                "node_execution_image": "greenline-node@sha256:" + "c" * 64,
            }
        ]


class _ReadyConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, *_args) -> _ReadyCursor:
        return _ReadyCursor(query)


class _ReadyPool:
    def connection(self, **_kwargs) -> _ReadyConnection:
        return _ReadyConnection()

    def close(self) -> None:
        return None


def _codes(error: CompositionError) -> set[str]:
    return {violation.code for violation in error.violations}


def test_runtime_mode_is_mandatory_and_exact() -> None:
    with pytest.raises(CompositionError) as missing:
        create_application({})
    assert _codes(missing.value) == {"missing_runtime_mode"}

    with pytest.raises(CompositionError) as invalid:
        create_application({"GREENLINE_MODE": "production"})
    assert _codes(invalid.value) == {"invalid_runtime_mode"}


def test_local_mode_becomes_ready_with_local_adapters() -> None:
    application = create_application({"GREENLINE_MODE": "local"})
    before_startup = TestClient(application).get("/health/ready")
    assert before_startup.status_code == 503
    assert before_startup.json()["status"] == "not_ready"

    with TestClient(application) as client:
        assert client.get("/health/live").json() == {
            "status": "live",
            "mode": "local",
        }
        assert client.get("/health/ready").json() == {
            "status": "ready",
            "mode": "local",
        }
        assert client.get("/health/release").json() == {
            "status": "ready",
            "source_sha": "development",
        }


def test_hosted_mode_reports_every_missing_safety_requirement() -> None:
    with pytest.raises(CompositionError) as raised:
        create_application({"GREENLINE_MODE": "hosted"})

    assert _codes(raised.value) == {
        "clerk_secret_required",
        "authorized_parties_required",
        "api_process_role_required",
        "durable_state_required",
        "distributed_coordination_required",
        "abuse_controls_required",
        "trusted_proxy_required",
        "trusted_proxy_launcher_required",
        "security_logging_required",
        "release_identity_required",
    }


def test_placeholder_adapters_cannot_bypass_the_hosted_gate() -> None:
    secret = "sk_test_must_not_appear"
    with pytest.raises(CompositionError) as raised:
        create_application(
            _hosted_environment(
                CLERK_SECRET_KEY=secret,
                CLERK_AUTHORIZED_PARTIES="https://app.example.com",
            ),
            hosted_adapters=object(),
        )

    assert _codes(raised.value) == {
        "durable_state_required",
        "distributed_coordination_required",
        "abuse_controls_required",
    }
    assert secret not in str(raised.value)


def test_postgres_learner_state_clears_only_the_durable_state_gate() -> None:
    durable_state = PostgresLearnerStateAdapter(pool=_ReadyPool())

    with pytest.raises(CompositionError) as raised:
        create_application(
            _hosted_environment(
                CLERK_SECRET_KEY="sk_test_example",
                CLERK_AUTHORIZED_PARTIES="https://app.example.com",
            ),
            hosted_adapters=HostedAdapters(
                learner_state=durable_state,
            ),
        )

    assert _codes(raised.value) == {
        "distributed_coordination_required",
        "abuse_controls_required",
    }


def test_postgres_run_jobs_clear_the_distributed_coordination_gate() -> None:
    durable_state = PostgresLearnerStateAdapter(pool=_ReadyPool())
    durable_jobs = PostgresRunJobAdapter(pool=_ReadyPool())

    with pytest.raises(CompositionError) as raised:
        create_application(
            _hosted_environment(
                CLERK_SECRET_KEY="sk_test_example",
                CLERK_AUTHORIZED_PARTIES="https://app.example.com",
            ),
            hosted_adapters=HostedAdapters(
                learner_state=durable_state,
                run_jobs=durable_jobs,
            ),
        )

    assert _codes(raised.value) == {"abuse_controls_required"}


def test_hosted_mode_composes_when_every_safety_adapter_is_ready() -> None:
    application = create_application(
        _hosted_environment(
            CLERK_SECRET_KEY="sk_test_example",
            CLERK_AUTHORIZED_PARTIES="https://app.example.com",
        ),
        hosted_adapters=HostedAdapters(
            learner_state=PostgresLearnerStateAdapter(pool=_ReadyPool()),
            run_jobs=PostgresRunJobAdapter(pool=_ReadyPool()),
            abuse_controls=PostgresAbuseControlAdapter(pool=_ReadyPool()),
        ),
    )

    assert application.state.runtime_settings.mode.value == "hosted"
    assert type(application.state.execution_adapter) is DisabledExecutionAdapter
    with TestClient(application) as client:
        assert client.get("/health/release").json() == {
            "status": "ready",
            "source_sha": "a" * 40,
            "worker": {
                "status": "ready",
                "live_workers": 1,
                "matching_workers": 1,
                "source_sha": "a" * 40,
                "python_execution_image": "greenline-python@sha256:" + "b" * 64,
                "node_execution_image": "greenline-node@sha256:" + "c" * 64,
            },
        }


class _NoWorkerCursor(_ReadyCursor):
    def fetchall(self) -> list[dict[str, str]]:
        return []


class _NoWorkerConnection(_ReadyConnection):
    def execute(self, query: str, *_args) -> _ReadyCursor:
        return _NoWorkerCursor(query)


class _NoWorkerPool(_ReadyPool):
    def connection(self, **_kwargs) -> _ReadyConnection:
        return _NoWorkerConnection()


def test_hosted_release_is_not_ready_without_a_live_worker_attestation() -> None:
    application = create_application(
        _hosted_environment(
            CLERK_SECRET_KEY="sk_test_example",
            CLERK_AUTHORIZED_PARTIES="https://app.example.com",
        ),
        hosted_adapters=HostedAdapters(
            learner_state=PostgresLearnerStateAdapter(pool=_NoWorkerPool()),
            run_jobs=PostgresRunJobAdapter(pool=_NoWorkerPool()),
            abuse_controls=PostgresAbuseControlAdapter(pool=_NoWorkerPool()),
        ),
    )

    with TestClient(application) as client:
        response = client.get("/health/release")
    assert response.status_code == 503
    assert response.json()["worker"] == {
        "status": "not_ready",
        "live_workers": 0,
        "matching_workers": 0,
        "source_sha": "a" * 40,
        "python_execution_image": None,
        "node_execution_image": None,
    }


def test_hosted_mode_requires_an_immutable_release_identity() -> None:
    with pytest.raises(CompositionError) as raised:
        create_application(
            _hosted_environment(GREENLINE_RELEASE_SHA="A" * 40)
        )

    assert "release_identity_required" in _codes(raised.value)


def test_hosted_mode_refuses_invalid_limit_configuration() -> None:
    with pytest.raises(CompositionError) as raised:
        create_application(
            _hosted_environment(
                GREENLINE_MAX_REQUEST_BYTES="0",
            )
        )

    assert "invalid_abuse_configuration" in _codes(raised.value)


def test_hosted_api_readiness_does_not_depend_on_execution_runtime() -> None:
    application = create_application(
        _hosted_environment(
            CLERK_SECRET_KEY="sk_test_example",
            CLERK_AUTHORIZED_PARTIES="https://app.example.com",
            GREENLINE_DOCKER_BINARY="definitely-not-present",
            GREENLINE_PYTHON_EXECUTION_IMAGE="not-a-digest",
        ),
        hosted_adapters=HostedAdapters(
            learner_state=PostgresLearnerStateAdapter(pool=_ReadyPool()),
            run_jobs=PostgresRunJobAdapter(pool=_ReadyPool()),
            abuse_controls=PostgresAbuseControlAdapter(pool=_ReadyPool()),
        ),
    )

    with TestClient(application) as client:
        assert client.get("/health/ready").status_code == 200
