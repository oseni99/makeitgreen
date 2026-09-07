from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from deploy import boot


UNAFFECTED_DEPLOYMENT_SETTINGS = [
    {},
    {"LOG_LEVEL": "debug"},
    {"REGION": "us-east-1"},
    {"PORT": "8080"},
    {"FEATURE_NOTIFICATIONS": "enabled"},
    {"WORKERS": "4"},
]


def test_explicit_configuration_override_still_boots() -> None:
    service = boot({"APP_CONFIG_MODULE": "deploy.config"})
    assert service.name == "notifications"
    assert service.environment == "production"


def test_health_contract_is_unchanged_after_boot() -> None:
    service = boot({"APP_CONFIG_MODULE": "deploy.config"})
    assert service.health() == {"status": "ok", "service": "notifications"}


def test_invalid_explicit_override_fails_loudly() -> None:
    with pytest.raises(ModuleNotFoundError):
        boot({"APP_CONFIG_MODULE": "deploy.missing_emergency_config"})


@pytest.mark.parametrize("settings", UNAFFECTED_DEPLOYMENT_SETTINGS)
def test_production_default_boots_after_module_rename(settings: dict[str, str]) -> None:
    service = boot(settings)
    assert service.name == "notifications"
    assert service.environment == "production"


@pytest.mark.parametrize("settings", UNAFFECTED_DEPLOYMENT_SETTINGS)
def test_recorded_production_command_reaches_healthy_startup(settings: dict[str, str]) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, **settings}
    environment.pop("APP_CONFIG_MODULE", None)

    completed = subprocess.run(
        [sys.executable, "-m", "deploy"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=5,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "service": "notifications",
        "status": "ok",
    }
