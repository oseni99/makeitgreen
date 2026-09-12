#!/usr/bin/env python3
"""Fail closed on unsafe or inconsistent two-host deployment configuration."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class DeploymentValidationError(ValueError):
    """One or more deployment contracts are unsafe or incomplete."""


DIGEST_REFERENCE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
POLICY_KEYS = (
    "MAX_REQUEST_BYTES",
    "REQUESTS_PER_MINUTE",
    "MUTATIONS_PER_MINUTE",
    "RUNS_PER_MINUTE",
    "CONTENT_READS_PER_MINUTE",
    "DISTINCT_CHALLENGES_PER_HOUR",
    "SOLUTIONS_PER_HOUR",
    "MAX_ACTIVE_RUNS",
    "MAX_ACTIVE_RUNS_PER_USER",
    "AUDIT_RETENTION_DAYS",
)
EXPECTED_APP_SERVICES = {"caddy", "control-plane", "postgres"}
EXPECTED_WORKER_SERVICES = {"execution-worker"}
RUN_BUNDLE_PATH = "/srv/makeitgreen/run-bundles"
RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
APP_SECRET_FILES = {
    "clerk_secret_key": "clerk_secret_key",
    "api_database_url": "api_database_url",
    "security_log_hmac_key": "security_log_hmac_key",
    "postgres_admin_password": "postgres_admin_password",
    "postgres_server_cert": "postgres_server.crt",
    "postgres_server_key": "postgres_server.key",
    "postgres_ca": "postgres_ca.crt",
}
WORKER_SECRET_FILES = {
    "worker_database_url": "worker_database_url",
    "security_log_hmac_key": "security_log_hmac_key",
    "postgres_ca": "postgres_ca.crt",
}


def load_env(path: Path) -> dict[str, str]:
    """Read a strict Compose env file without executing it as shell code."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DeploymentValidationError(f"cannot read {path}") from exc
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or "=" not in line:
            raise DeploymentValidationError(
                f"{path}:{line_number} must use KEY=value syntax"
            )
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise DeploymentValidationError(
                f"{path}:{line_number} has an invalid environment name"
            )
        if key in values:
            raise DeploymentValidationError(f"{path} defines {key} more than once")
        if value != value.strip() or value.startswith(("'", '"')):
            raise DeploymentValidationError(
                f"{path}:{line_number} must use an unquoted, trimmed value"
            )
        values[key] = value
    return values


def _required(values: dict[str, str], key: str, source: str) -> str:
    value = values.get(key, "")
    if not value:
        raise DeploymentValidationError(f"{source} must define {key}")
    return value


def _positive_integer(
    values: dict[str, str], key: str, source: str, *, minimum: int = 1, maximum: int | None = None
) -> int:
    raw = _required(values, key, source)
    try:
        value = int(raw)
    except ValueError as exc:
        raise DeploymentValidationError(f"{source} {key} must be an integer") from exc
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise DeploymentValidationError(f"{source} {key} must be {bound}")
    return value


def validate_settings(
    app_release: dict[str, str],
    app_runtime: dict[str, str],
    worker_release: dict[str, str],
    worker_runtime: dict[str, str],
) -> None:
    image_groups = {
        "app release": ("CONTROL_PLANE_IMAGE", "CADDY_IMAGE", "POSTGRES_IMAGE"),
        "worker release": (
            "EXECUTION_WORKER_IMAGE",
            "PYTHON_EXECUTION_IMAGE",
            "NODE_EXECUTION_IMAGE",
        ),
    }
    for source, keys in image_groups.items():
        values = app_release if source == "app release" else worker_release
        for key in keys:
            reference = _required(values, key, source)
            if not DIGEST_REFERENCE.fullmatch(reference):
                raise DeploymentValidationError(
                    f"{source} {key} must be an exact @sha256 digest reference"
                )

    domain = _required(app_runtime, "APP_DOMAIN", "app runtime")
    if not HOSTNAME.fullmatch(domain):
        raise DeploymentValidationError("APP_DOMAIN must be a lowercase DNS hostname")
    if _required(app_runtime, "CLERK_AUTHORIZED_PARTIES", "app runtime") != f"https://{domain}":
        raise DeploymentValidationError(
            "CLERK_AUTHORIZED_PARTIES must be the exact HTTPS application origin"
        )

    try:
        postgres_ip = ipaddress.ip_address(
            _required(app_runtime, "POSTGRES_BIND_IP", "app runtime")
        )
    except ValueError as exc:
        raise DeploymentValidationError("POSTGRES_BIND_IP must be an IP address") from exc
    if postgres_ip.version != 4 or not any(
        postgres_ip in network for network in RFC1918_NETWORKS
    ):
        raise DeploymentValidationError(
            "POSTGRES_BIND_IP must be an IPv4 RFC1918 private VPC address"
        )

    try:
        proxy_subnet = ipaddress.ip_network(
            _required(app_runtime, "PROXY_SUBNET", "app runtime"), strict=True
        )
    except ValueError as exc:
        raise DeploymentValidationError("PROXY_SUBNET must be an explicit CIDR") from exc
    if not proxy_subnet.is_private or proxy_subnet != ipaddress.ip_network("172.30.0.0/24"):
        raise DeploymentValidationError(
            "PROXY_SUBNET must remain 172.30.0.0/24 to match fixed service addresses"
        )

    for key in POLICY_KEYS:
        app_value = _positive_integer(app_runtime, key, "app runtime")
        worker_value = _positive_integer(worker_runtime, key, "worker runtime")
        if app_value != worker_value:
            raise DeploymentValidationError(
                f"{key} must match on the application and every worker host"
            )
    if int(app_runtime["MAX_ACTIVE_RUNS_PER_USER"]) > int(app_runtime["MAX_ACTIVE_RUNS"]):
        raise DeploymentValidationError(
            "MAX_ACTIVE_RUNS_PER_USER cannot exceed MAX_ACTIVE_RUNS"
        )
    if not (
        int(app_runtime["RUNS_PER_MINUTE"])
        <= int(app_runtime["MUTATIONS_PER_MINUTE"])
        <= int(app_runtime["REQUESTS_PER_MINUTE"])
    ):
        raise DeploymentValidationError(
            "run, mutation, and total request limits must be nested"
        )

    _positive_integer(worker_runtime, "DOCKER_GID", "worker runtime")
    _positive_integer(
        worker_runtime, "RUN_MEMORY_MIB", "worker runtime", minimum=128, maximum=4096
    )
    _positive_integer(
        worker_runtime, "WORKER_CONCURRENCY", "worker runtime", minimum=1, maximum=32
    )
    bundle_path = _required(worker_runtime, "RUN_BUNDLE_DIR", "worker runtime")
    if bundle_path != RUN_BUNDLE_PATH:
        raise DeploymentValidationError(
            f"RUN_BUNDLE_DIR must be the shared host/container path {RUN_BUNDLE_PATH}"
        )


def _secret_text(path: Path, label: str) -> str:
    try:
        if not path.is_file() or path.is_symlink():
            raise DeploymentValidationError(f"{label} must be a regular non-symlink file")
        if path.stat().st_size > 65_536:
            raise DeploymentValidationError(f"{label} exceeds 65536 bytes")
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise DeploymentValidationError(f"cannot read {label}") from exc
    if not value:
        raise DeploymentValidationError(f"{label} must not be empty")
    return value


def _validate_database_url(path: Path, label: str) -> None:
    parsed = urlparse(_secret_text(path, label))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise DeploymentValidationError(f"{label} must contain a PostgreSQL URL")
    query = parse_qs(parsed.query)
    if query.get("sslmode") != ["verify-full"]:
        raise DeploymentValidationError(f"{label} must use sslmode=verify-full")
    if query.get("sslrootcert") != ["/run/secrets/postgres_ca"]:
        raise DeploymentValidationError(
            f"{label} must verify /run/secrets/postgres_ca"
        )


def validate_secrets(app_root: Path, worker_root: Path) -> None:
    app_secrets = app_root / "secrets"
    worker_secrets = worker_root / "secrets"
    _validate_database_url(app_secrets / "api_database_url", "API database URL")
    _validate_database_url(
        worker_secrets / "worker_database_url", "worker database URL"
    )
    if not _secret_text(app_secrets / "clerk_secret_key", "Clerk secret").startswith(
        "sk_live_"
    ):
        raise DeploymentValidationError("Clerk secret must be a production sk_live_ key")
    app_hmac = _secret_text(app_secrets / "security_log_hmac_key", "app HMAC key")
    worker_hmac = _secret_text(
        worker_secrets / "security_log_hmac_key", "worker HMAC key"
    )
    if len(app_hmac.encode()) < 32 or app_hmac != worker_hmac:
        raise DeploymentValidationError(
            "app and worker HMAC keys must match and contain at least 32 bytes"
        )
    for root, names in (
        (
            app_secrets,
            (
                "postgres_admin_password",
                "postgres_server.crt",
                "postgres_server.key",
                "postgres_ca.crt",
            ),
        ),
        (worker_secrets, ("postgres_ca.crt",)),
    ):
        for name in names:
            _secret_text(root / name, name)


def _compose_model(root: Path, compose_name: str) -> dict[str, object]:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(root / "release.env"),
        "--env-file",
        str(root / "runtime.env"),
        "-f",
        str(root / compose_name),
        "config",
        "--format",
        "json",
    ]
    try:
        completed = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=30
        )
        model = json.loads(completed.stdout)
    except FileNotFoundError as exc:
        raise DeploymentValidationError("docker compose is required") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        detail = getattr(exc, "stderr", "") or "invalid Compose model"
        raise DeploymentValidationError(f"cannot render {compose_name}: {detail.strip()}") from exc
    if not isinstance(model, dict):
        raise DeploymentValidationError(f"{compose_name} did not render an object")
    return model


def _volume_targets(service: dict[str, object]) -> dict[str, dict[str, object]]:
    volumes = service.get("volumes", [])
    if not isinstance(volumes, list):
        return {}
    return {
        str(volume.get("target")): volume
        for volume in volumes
        if isinstance(volume, dict) and volume.get("target")
    }


def _secret_sources(service: dict[str, object]) -> set[str]:
    secrets = service.get("secrets", [])
    if not isinstance(secrets, list):
        return set()
    return {
        str(secret.get("source"))
        for secret in secrets
        if isinstance(secret, dict) and secret.get("source")
    }


def validate_effective_secret_files(
    model: dict[str, object], root: Path, expected: dict[str, str]
) -> None:
    """Require every rendered secret mount to stay under this deployment root."""
    secrets = model.get("secrets")
    if not isinstance(secrets, dict) or set(secrets) != set(expected):
        raise DeploymentValidationError("deployment has an incorrect secret file set")
    for secret_name, file_name in expected.items():
        configuration = secrets[secret_name]
        if not isinstance(configuration, dict):
            raise DeploymentValidationError("deployment has an invalid secret source")
        rendered_file = configuration.get("file")
        if not isinstance(rendered_file, str) or Path(rendered_file).resolve() != (
            root / "secrets" / file_name
        ).resolve():
            raise DeploymentValidationError(
                f"{secret_name} must use its fixed deployment-relative secret file"
            )


def validate_compose_models(app: dict[str, object], worker: dict[str, object]) -> None:
    app_services = app.get("services")
    worker_services = worker.get("services")
    if not isinstance(app_services, dict) or set(app_services) != EXPECTED_APP_SERVICES:
        raise DeploymentValidationError("application Compose must contain exactly three services")
    if not isinstance(worker_services, dict) or set(worker_services) != EXPECTED_WORKER_SERVICES:
        raise DeploymentValidationError("worker Compose must contain only execution-worker")

    for name, raw_service in app_services.items():
        if not isinstance(raw_service, dict):
            raise DeploymentValidationError(f"invalid application service {name}")
        if "/var/run/docker.sock" in _volume_targets(raw_service):
            raise DeploymentValidationError("the application host must not mount Docker")
        ports = raw_service.get("ports", [])
        if name == "control-plane" and ports:
            raise DeploymentValidationError("control-plane must not publish a host port")
        if name == "caddy" and not ports:
            raise DeploymentValidationError("Caddy must publish HTTPS entry points")
        if not raw_service.get("healthcheck"):
            raise DeploymentValidationError(f"{name} must have a healthcheck")

    postgres = app_services["postgres"]
    postgres_ports = postgres.get("ports", [])
    if not isinstance(postgres_ports, list) or len(postgres_ports) != 1:
        raise DeploymentValidationError("PostgreSQL must publish one private VPC port")
    postgres_port = postgres_ports[0]
    if not isinstance(postgres_port, dict) or not postgres_port.get("host_ip"):
        raise DeploymentValidationError("PostgreSQL port must bind an explicit private IP")

    control = app_services["control-plane"]
    if not control.get("read_only") or set(control.get("cap_drop", [])) != {"ALL"}:
        raise DeploymentValidationError("control-plane must use a read-only, capability-free root")
    if _secret_sources(control) != {
        "clerk_secret_key",
        "api_database_url",
        "security_log_hmac_key",
        "postgres_ca",
    }:
        raise DeploymentValidationError("control-plane has an incorrect secret boundary")
    expected_networks = {
        "caddy": {"proxy"},
        "control-plane": {"proxy", "database"},
        "postgres": {"database"},
    }
    for name, networks in expected_networks.items():
        configured = app_services[name].get("networks", {})
        if not isinstance(configured, dict) or set(configured) != networks:
            raise DeploymentValidationError(
                f"{name} is attached to the wrong application trust network"
            )
    app_networks = app.get("networks", {})
    database_network = (
        app_networks.get("database", {}) if isinstance(app_networks, dict) else {}
    )
    if not isinstance(database_network, dict) or database_network.get("internal"):
        raise DeploymentValidationError(
            "database network must allow the published private VPC port"
        )

    execution_worker = worker_services["execution-worker"]
    if not isinstance(execution_worker, dict):
        raise DeploymentValidationError("execution-worker service is invalid")
    if execution_worker.get("ports"):
        raise DeploymentValidationError("execution-worker must not publish a port")
    if not execution_worker.get("read_only") or set(execution_worker.get("cap_drop", [])) != {"ALL"}:
        raise DeploymentValidationError("execution-worker must use a read-only, capability-free root")
    if not execution_worker.get("healthcheck"):
        raise DeploymentValidationError("execution-worker must retain its image healthcheck")
    worker_targets = _volume_targets(execution_worker)
    if "/var/run/docker.sock" not in worker_targets:
        raise DeploymentValidationError("execution-worker must mount the local Docker socket")
    bundle = worker_targets.get(RUN_BUNDLE_PATH)
    if not bundle or bundle.get("source") != RUN_BUNDLE_PATH:
        raise DeploymentValidationError("Run Bundle source and target must be identical")
    worker_secrets = _secret_sources(execution_worker)
    if worker_secrets != {"worker_database_url", "security_log_hmac_key", "postgres_ca"}:
        raise DeploymentValidationError("execution-worker has an incorrect secret boundary")

    # Compose interpolates shell variables ahead of env files. Validate the
    # settings containers will actually receive, not just their input files.
    control_env = control.get("environment", {})
    worker_env = execution_worker.get("environment", {})
    caddy_env = app_services["caddy"].get("environment", {})
    proxy_network = app_networks.get("proxy", {})
    proxy_configs = proxy_network.get("ipam", {}).get("config", [])
    docker_groups = execution_worker.get("group_add", [])
    if (
        not all(isinstance(env, dict) for env in (control_env, worker_env, caddy_env))
        or len(proxy_configs) != 1
        or len(docker_groups) != 1
    ):
        raise DeploymentValidationError("invalid effective Compose settings")
    validate_settings(
        {
            "CONTROL_PLANE_IMAGE": control.get("image", ""),
            "CADDY_IMAGE": app_services["caddy"].get("image", ""),
            "POSTGRES_IMAGE": postgres.get("image", ""),
        },
        {
            "APP_DOMAIN": caddy_env.get("APP_DOMAIN", ""),
            "CLERK_AUTHORIZED_PARTIES": control_env.get("CLERK_AUTHORIZED_PARTIES", ""),
            "POSTGRES_BIND_IP": postgres_port["host_ip"],
            "PROXY_SUBNET": proxy_configs[0].get("subnet", ""),
            **{key: control_env.get(f"GREENLINE_{key}", "") for key in POLICY_KEYS},
        },
        {
            "EXECUTION_WORKER_IMAGE": execution_worker.get("image", ""),
            "PYTHON_EXECUTION_IMAGE": worker_env.get("GREENLINE_PYTHON_EXECUTION_IMAGE", ""),
            "NODE_EXECUTION_IMAGE": worker_env.get("GREENLINE_NODE_EXECUTION_IMAGE", ""),
        },
        {
            "DOCKER_GID": str(docker_groups[0]),
            **{
                key: worker_env.get(f"GREENLINE_{key}", "")
                for key in (*POLICY_KEYS, "RUN_MEMORY_MIB", "WORKER_CONCURRENCY", "RUN_BUNDLE_DIR")
            },
        },
    )


def validate_caddyfile(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        "reverse_proxy control-plane:8000",
        "max_size 256KB",
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "https://clerk.makeitgreen.dev",
        "format json",
    )
    if any(item not in text for item in required):
        raise DeploymentValidationError("Caddyfile is missing a required edge control")


def validate(app_root: Path, worker_root: Path, *, check_secrets: bool = True) -> None:
    app_release = load_env(app_root / "release.env")
    app_runtime = load_env(app_root / "runtime.env")
    worker_release = load_env(worker_root / "release.env")
    worker_runtime = load_env(worker_root / "runtime.env")
    validate_settings(app_release, app_runtime, worker_release, worker_runtime)
    if check_secrets:
        validate_secrets(app_root, worker_root)
    validate_caddyfile(app_root / "Caddyfile")
    app_model = _compose_model(app_root, "compose.app.yaml")
    worker_model = _compose_model(worker_root, "compose.worker.yaml")
    validate_effective_secret_files(app_model, app_root, APP_SECRET_FILES)
    validate_effective_secret_files(worker_model, worker_root, WORKER_SECRET_FILES)
    validate_compose_models(app_model, worker_model)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--worker-root", type=Path, required=True)
    parser.add_argument(
        "--skip-secrets",
        action="store_true",
        help="validate templates before real secret files are installed",
    )
    args = parser.parse_args()
    try:
        validate(
            args.app_root.resolve(),
            args.worker_root.resolve(),
            check_secrets=not args.skip_secrets,
        )
    except (DeploymentValidationError, OSError) as exc:
        print(f"deployment validation failed: {exc}", file=sys.stderr)
        return 1
    print("deployment validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
