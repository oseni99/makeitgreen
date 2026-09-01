"""Cached, per-requirements Python execution environments."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from threading import Lock

from challenges import DATA_DIR

ENVIRONMENTS_DIR = DATA_DIR / "environments"
_locks_guard = Lock()
_locks: dict[str, Lock] = {}


def _environment_key(requirements: bytes) -> str:
    payload = f"{sys.version_info.major}.{sys.version_info.minor}\0".encode() + requirements
    return hashlib.sha256(payload).hexdigest()


def python_for(requirements_file: Path | None) -> str:
    """Return the current Python or a cached environment for declared deps."""
    if requirements_file is None:
        return sys.executable
    requirements = requirements_file.read_bytes()
    key = _environment_key(requirements)
    env_dir = ENVIRONMENTS_DIR / key
    python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file():
        return str(python)
    with _locks_guard:
        lock = _locks.setdefault(key, Lock())
    with lock:
        if python.is_file():
            return str(python)
        ENVIRONMENTS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".{key}-", dir=ENVIRONMENTS_DIR))
        try:
            venv.EnvBuilder(with_pip=True, system_site_packages=True).create(tmp)
            tmp_python = tmp / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(
                [str(tmp_python), "-m", "pip", "install", "-r", str(requirements_file)],
                check=True,
            )
            try:
                tmp.replace(env_dir)
            except FileExistsError:
                shutil.rmtree(tmp)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    return str(python)
