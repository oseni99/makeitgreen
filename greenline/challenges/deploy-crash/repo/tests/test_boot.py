from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from deploy import boot


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


def test_production_default_boots_after_module_rename() -> None:
    service = boot({})

    assert service.name == "notifications"
    assert service.environment == "production"


def test_recorded_production_command_reaches_healthy_startup() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [sys.executable, "-m", "deploy"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "service": "notifications",
        "status": "ok",
    }
