from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Mapping


# BUG: this module was renamed to deploy.config in release 2026.08.30.
DEFAULT_CONFIG_MODULE = "deploy.settings"


@dataclass(frozen=True)
class Service:
    name: str
    environment: str

    def health(self) -> dict[str, str]:
        return {"status": "ok", "service": self.name}


def _load_config(module_name: str) -> ModuleType:
    return importlib.import_module(module_name)


def boot(environ: Mapping[str, str] | None = None) -> Service:
    env = environ or {}
    module_name = env.get("APP_CONFIG_MODULE", DEFAULT_CONFIG_MODULE)
    config = _load_config(module_name)
    return Service(name=config.SERVICE_NAME, environment=config.ENVIRONMENT)
