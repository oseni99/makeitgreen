#!/usr/bin/env python3
"""Assert every challenge's pristine repo fails and its solution overlay passes.

Runnable as `python scripts/validate_challenges.py` from greenline/, or via an
absolute path. Discovers challenges next to this script's parent directory.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IGNORED = {"__pycache__", ".pytest_cache", ".git", ".venv"}
PYTEST_CONFIG_FILES = {
    "pytest.ini",
    ".pytest.ini",
    "pyproject.toml",
    "tox.ini",
    "setup.cfg",
}
TIMEOUT_SECONDS = 60

CHALLENGES_DIR = Path(__file__).resolve().parent.parent / "challenges"
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


class ProtectedSolutionPath(ValueError):
    """A reference solution attempts to replace protected challenge content."""


def discover_slugs() -> list[str]:
    if not CHALLENGES_DIR.is_dir():
        return []
    return sorted(
        child.name
        for child in CHALLENGES_DIR.iterdir()
        if child.is_dir() and (child / "challenge.json").is_file()
    )


def load_metadata(challenge: Path) -> dict[str, object]:
    metadata_path = challenge / "challenge.json"
    if not metadata_path.is_file():
        return {}
    try:
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ValueError("invalid challenge metadata") from exc
    if not isinstance(meta, dict):
        raise ValueError("challenge metadata must be an object")
    return meta


def runtime_config(challenge: Path) -> tuple[list[str], str]:
    meta = load_metadata(challenge)
    runtime = meta.get("runtime") or {}
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    kind = runtime.get("kind", "python")
    if kind not in {"python", "node"}:
        raise ValueError("runtime.kind must be python or node")
    report = runtime.get("report", "pytest-json" if kind == "python" else "text")
    if report not in {"pytest-json", "text"}:
        raise ValueError("runtime.report must be pytest-json or text")
    command = runtime.get("command")
    if command is None:
        if kind != "python":
            raise ValueError("non-Python runtimes require runtime.command")
        command = ["{python}", "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider"]
    if not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command):
        raise ValueError("runtime.command must be a non-empty string array")
    requirements = runtime.get("requirements")
    if requirements is not None:
        if not isinstance(requirements, str) or Path(requirements).is_absolute() or ".." in Path(requirements).parts:
            raise ValueError("runtime.requirements must be a safe relative path")
        if not (challenge / "repo" / requirements).is_file():
            raise ValueError("runtime.requirements does not exist")
    return command, report


def run_pytest(workdir: Path) -> tuple[int, str]:
    """Run the legacy/default Python contract.

    Kept as a narrow public seam because backend regression tests and external
    authoring tools patch it when validating red/green exit semantics.
    """
    return _run_command(
        [sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider"],
        workdir,
    )


def _run_command(command: list[str], workdir: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output = stdout + ("\n" + stderr if stderr.strip() else "")
        output += f"\nTIMEOUT: test command exceeded {TIMEOUT_SECONDS}s"
        return -1, output

    output = proc.stdout + ("\n" + proc.stderr if proc.stderr.strip() else "")
    return proc.returncode, output


def run_suite(challenge: Path, workdir: Path) -> tuple[int, str]:
    metadata_path = challenge / "challenge.json"
    if not metadata_path.is_file():
        return run_pytest(workdir)
    meta = load_metadata(challenge)
    if not meta.get("runtime"):
        return run_pytest(workdir)
    command, _report = runtime_config(challenge)
    runtime = meta.get("runtime") or {}
    python = sys.executable
    requirements_name = runtime.get("requirements")
    if requirements_name:
        # Use the same content-addressed environment contract as the platform
        # runner so validation exercises dependency-isolated challenges too.
        sys.path.insert(0, str(BACKEND_DIR))
        try:
            from environments import python_for

            python = python_for(challenge / "repo" / requirements_name)
        finally:
            sys.path.remove(str(BACKEND_DIR))
    substitutions = {"{python}": python, "{repo}": str(workdir), "{json_report}": str(workdir / ".report.json")}
    resolved = [substitutions.get(part, part) for part in command]
    return _run_command(resolved, workdir)


def copy_repo(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*IGNORED))


def _matches_prefix(rel: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    return bool(prefix) and (rel == prefix or rel.startswith(f"{prefix}/"))


def overlay_solution(
    repo_copy: Path,
    solution_dir: Path,
    meta: dict[str, object] | None = None,
) -> None:
    meta = meta or {}
    if not solution_dir.is_dir():
        return
    for src in solution_dir.rglob("*"):
        if not src.is_file():
            continue
        if any(part in IGNORED for part in src.parts):
            continue
        rel = src.relative_to(solution_dir).as_posix()
        if rel == "SOLUTION.md":
            continue
        path = Path(rel)
        if path.name == "conftest.py" or (
            len(path.parts) == 1 and rel in PYTEST_CONFIG_FILES
        ):
            raise ProtectedSolutionPath(rel)
        runtime = meta.get("runtime")
        if isinstance(runtime, dict) and rel == runtime.get("requirements"):
            raise ProtectedSolutionPath(rel)
        readonly = meta.get("readonly", ["tests/"])
        if isinstance(readonly, list) and any(
            isinstance(prefix, str) and _matches_prefix(rel, prefix)
            for prefix in readonly
        ):
            raise ProtectedSolutionPath(rel)
        dest = repo_copy / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)


def _ok(label: str) -> str:
    return f"{label}  [OK]"


def _fail(label: str) -> str:
    return f"{label}  [FAIL]"


def validate_challenge(slug: str) -> bool:
    challenge = CHALLENGES_DIR / slug
    repo = challenge / "repo"
    solution = challenge / "solution"
    print(f"== {slug}")

    if not repo.is_dir():
        print(_fail("   pristine : missing repo/"))
        print(_fail("   solution : skipped (no repo/)"))
        return False

    passed = True
    with tempfile.TemporaryDirectory(prefix=f"greenline-validate-{slug}-") as tmp:
        tmpdir = Path(tmp)
        pristine = tmpdir / "pristine"
        copy_repo(repo, pristine)
        try:
            exit_code, output = run_suite(challenge, pristine)
        except ValueError as exc:
            print(_fail(f"   metadata : {exc}"))
            return False
        if exit_code == 1:
            print(_ok(f"   pristine : exit {exit_code}  (expected fail)"))
        else:
            print(_fail(f"   pristine : exit {exit_code}  (expected test-failure exit 1)"))
            print(_tail(output))
            passed = False

        overlaid = tmpdir / "solution"
        copy_repo(repo, overlaid)
        try:
            meta = load_metadata(challenge)
            overlay_solution(overlaid, solution, meta)
        except ProtectedSolutionPath as exc:
            print(_fail(f"   solution : protected path {exc}"))
            return False
        exit_code, output = run_suite(challenge, overlaid)
        if exit_code == 0:
            print(_ok("   solution : exit 0  (expected pass)"))
        else:
            print(_fail(f"   solution : exit {exit_code}  (expected pass)"))
            print(_tail(output))
            passed = False

    return passed


def _tail(output: str, limit: int = 40) -> str:
    lines = output.strip().splitlines()
    snippet = "\n".join(lines[-limit:])
    return f"      ---- pytest output (tail) ----\n      {snippet.replace(chr(10), chr(10) + '      ')}"


def main() -> int:
    slugs = discover_slugs()
    print(f"Validating {len(slugs)} challenge(s) in {CHALLENGES_DIR}")
    if not slugs:
        print("No challenges found (expected */challenge.json).")
        return 1

    failures: list[str] = []
    for slug in slugs:
        if not validate_challenge(slug):
            failures.append(slug)

    print()
    if failures:
        print(f"{len(failures)}/{len(slugs)} challenge(s) failed: {', '.join(failures)}")
        return 1
    print(f"{len(slugs)}/{len(slugs)} challenges valid (pristine fails, solution passes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
