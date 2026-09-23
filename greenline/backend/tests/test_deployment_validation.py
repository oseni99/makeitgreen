"""Behavioral tests for the two-host deployment preflight boundary."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_deployment.py"
SPEC = importlib.util.spec_from_file_location("validate_deployment", MODULE_PATH)
assert SPEC and SPEC.loader
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)


def _digest(name: str) -> str:
    return f"registry.example/{name}@sha256:" + "a" * 64


def _settings() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    policy = {
        "MAX_REQUEST_BYTES": "262144",
        "REQUESTS_PER_MINUTE": "240",
        "MUTATIONS_PER_MINUTE": "30",
        "RUNS_PER_MINUTE": "6",
        "CONTENT_READS_PER_MINUTE": "120",
        "DISTINCT_CHALLENGES_PER_HOUR": "20",
        "SOLUTIONS_PER_HOUR": "5",
        "MAX_ACTIVE_RUNS": "100",
        "MAX_ACTIVE_RUNS_PER_USER": "1",
        "AUDIT_RETENTION_DAYS": "30",
    }
    return (
        {
            "CONTROL_PLANE_IMAGE": _digest("control"),
            "CADDY_IMAGE": _digest("caddy"),
            "POSTGRES_IMAGE": _digest("postgres"),
        },
        {
            "APP_DOMAIN": "makeitgreen.dev",
            "CLERK_AUTHORIZED_PARTIES": "https://makeitgreen.dev",
            "POSTGRES_BIND_IP": "10.0.0.10",
            "PROXY_SUBNET": "172.30.0.0/24",
            **policy,
        },
        {
            "EXECUTION_WORKER_IMAGE": _digest("worker"),
            "PYTHON_EXECUTION_IMAGE": _digest("python"),
            "NODE_EXECUTION_IMAGE": _digest("node"),
        },
        {
            "DOCKER_GID": "999",
            "RUN_BUNDLE_DIR": "/srv/makeitgreen/run-bundles",
            "RUN_MEMORY_MIB": "384",
            "WORKER_CONCURRENCY": "1",
            **policy,
        },
    )


def test_safe_two_host_settings_pass() -> None:
    deployment.validate_settings(*_settings())


def test_runtime_grants_allow_worker_product_event_conflict_detection() -> None:
    grants = (
        ROOT / "deploy" / "app" / "postgres" / "runtime-role-grants.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(grants.split())

    assert (
        "GRANT SELECT (user_id, dedupe_key) ON product_events TO greenline_worker;"
        in normalized
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda values: values[0].update({"CONTROL_PLANE_IMAGE": "repo/app:latest"}),
            "exact @sha256",
        ),
        (
            lambda values: values[1].update({"POSTGRES_BIND_IP": "0.0.0.0"}),
            "private VPC",
        ),
        (
            lambda values: values[1].update({"POSTGRES_BIND_IP": "169.254.1.1"}),
            "RFC1918",
        ),
        (
            lambda values: values[1].update({"POSTGRES_BIND_IP": "192.0.2.1"}),
            "RFC1918",
        ),
        (
            lambda values: values[3].update({"MAX_ACTIVE_RUNS": "99"}),
            "must match",
        ),
        (
            lambda values: values[3].update({"RUN_BUNDLE_DIR": "/tmp/bundles"}),
            "shared host/container path",
        ),
    ],
)
def test_unsafe_or_inconsistent_settings_fail(mutation, message: str) -> None:
    values = _settings()
    mutation(values)
    with pytest.raises(deployment.DeploymentValidationError, match=message):
        deployment.validate_settings(*values)


def test_strict_env_reader_rejects_duplicate_values(tmp_path: Path) -> None:
    path = tmp_path / "runtime.env"
    path.write_text("MAX_ACTIVE_RUNS=100\nMAX_ACTIVE_RUNS=50\n", encoding="utf-8")

    with pytest.raises(deployment.DeploymentValidationError, match="more than once"):
        deployment.load_env(path)


def test_database_secret_requires_full_certificate_verification(tmp_path: Path) -> None:
    path = tmp_path / "database_url"
    path.write_text(
        "postgresql://runtime:secret@10.0.0.10/greenline?sslmode=require",
        encoding="utf-8",
    )

    with pytest.raises(deployment.DeploymentValidationError, match="verify-full"):
        deployment._validate_database_url(path, "database URL")


def test_worker_model_rejects_a_clerk_secret() -> None:
    app = {
        "services": {
            "caddy": {
                "ports": [{"target": 443}],
                "healthcheck": {"test": ["ok"]},
                "networks": {"proxy": {}},
            },
            "control-plane": {
                "read_only": True,
                "cap_drop": ["ALL"],
                "healthcheck": {"test": ["ok"]},
                "networks": {"proxy": {}, "database": {}},
                "secrets": [
                    {"source": name}
                    for name in (
                        "clerk_secret_key",
                        "clerk_jwt_key",
                        "api_database_url",
                        "security_log_hmac_key",
                        "postgres_ca",
                    )
                ],
            },
            "postgres": {
                "ports": [{"target": 5432, "host_ip": "10.0.0.10"}],
                "healthcheck": {"test": ["ok"]},
                "networks": {"database": {}},
            },
        },
        "networks": {"proxy": {}, "database": {}},
    }
    worker = {
        "services": {
            "execution-worker": {
                "read_only": True,
                "cap_drop": ["ALL"],
                "healthcheck": {"test": ["ok"]},
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/var/run/docker.sock",
                        "target": "/var/run/docker.sock",
                    },
                    {
                        "type": "bind",
                        "source": deployment.RUN_BUNDLE_PATH,
                        "target": deployment.RUN_BUNDLE_PATH,
                    },
                ],
                "secrets": [
                    {"source": "worker_database_url"},
                    {"source": "security_log_hmac_key"},
                    {"source": "postgres_ca"},
                    {"source": "clerk_secret_key"},
                ],
            }
        }
    }

    with pytest.raises(deployment.DeploymentValidationError, match="secret boundary"):
        deployment.validate_compose_models(app, worker)


@pytest.fixture
def prepared_deployment(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose unavailable")
    app_root = tmp_path / "app"
    worker_root = tmp_path / "worker"
    shutil.copytree(ROOT / "deploy" / "app", app_root)
    shutil.copytree(ROOT / "deploy" / "worker", worker_root)
    app_release, app_runtime, worker_release, worker_runtime = _settings()
    for key in {*app_release, *app_runtime, *worker_release, *worker_runtime}:
        monkeypatch.delenv(key, raising=False)
    for path, values in (
        (app_root / "release.env", app_release),
        (app_root / "runtime.env", app_runtime),
        (worker_root / "release.env", worker_release),
        (worker_root / "runtime.env", worker_runtime),
    ):
        path.write_text(
            "".join(f"{key}={value}\n" for key, value in values.items()),
            encoding="utf-8",
        )

    return app_root, worker_root


def test_checked_in_compose_models_render_with_safe_boundaries(prepared_deployment) -> None:
    deployment.validate(*prepared_deployment, check_secrets=False)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("POSTGRES_BIND_IP", "0.0.0.0", "private VPC"),
        ("POSTGRES_BIND_IP", "8.8.8.8", "private VPC"),
        ("POSTGRES_BIND_IP", "169.254.1.1", "RFC1918"),
        ("POSTGRES_BIND_IP", "192.0.2.1", "RFC1918"),
        ("POSTGRES_BIND_IP", "fd00::1", "RFC1918"),
        ("CONTROL_PLANE_IMAGE", "registry.example/control:latest", "exact @sha256"),
        ("CADDY_IMAGE", "caddy:latest", "exact @sha256"),
        ("POSTGRES_IMAGE", "postgres:latest", "exact @sha256"),
        ("EXECUTION_WORKER_IMAGE", "registry.example/worker:latest", "exact @sha256"),
        ("PYTHON_EXECUTION_IMAGE", "registry.example/python:latest", "exact @sha256"),
        ("NODE_EXECUTION_IMAGE", "registry.example/node:latest", "exact @sha256"),
        ("WORKER_CONCURRENCY", "33", "1..32"),
        ("MAX_ACTIVE_RUNS", "0", ">= 1"),
    ],
)
def test_unsafe_shell_overrides_are_rejected(prepared_deployment, monkeypatch, key, value, message):
    monkeypatch.setenv(key, value)
    with pytest.raises(deployment.DeploymentValidationError, match=message):
        deployment.validate(*prepared_deployment, check_secrets=False)


def test_effective_policy_must_match_between_hosts(prepared_deployment):
    _, worker_root = prepared_deployment
    compose = worker_root / "compose.worker.yaml"
    compose.write_text(compose.read_text().replace(
        "GREENLINE_MAX_ACTIVE_RUNS: ${MAX_ACTIVE_RUNS:?set MAX_ACTIVE_RUNS}",
        "GREENLINE_MAX_ACTIVE_RUNS: 99",
    ))
    with pytest.raises(deployment.DeploymentValidationError, match="must match"):
        deployment.validate(*prepared_deployment, check_secrets=False)


def test_shell_cannot_redirect_effective_secret_files(
    prepared_deployment, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path / "unvalidated-secrets"))

    deployment.validate(*prepared_deployment, check_secrets=False)


def test_changed_secret_source_is_rejected(prepared_deployment, tmp_path: Path) -> None:
    app_root, _ = prepared_deployment
    compose = app_root / "compose.app.yaml"
    compose.write_text(
        compose.read_text().replace(
            "file: ./secrets/clerk_secret_key",
            f"file: {tmp_path}/unvalidated-clerk-secret",
        )
    )

    with pytest.raises(deployment.DeploymentValidationError, match="fixed deployment-relative"):
        deployment.validate(*prepared_deployment, check_secrets=False)


def test_database_network_must_support_cross_host_workers(prepared_deployment):
    app_root, _ = prepared_deployment
    compose = app_root / "compose.app.yaml"
    compose.write_text(compose.read_text().replace(
        "  database:\n    driver: bridge", "  database:\n    internal: true\n    driver: bridge"
    ))
    with pytest.raises(deployment.DeploymentValidationError, match="published private VPC port"):
        deployment.validate(*prepared_deployment, check_secrets=False)
