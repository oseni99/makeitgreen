#!/usr/bin/env python3
"""Assert every challenge's pristine repo fails and its solution overlay passes.

Runnable as `python scripts/validate_challenges.py` from greenline/, or via an
absolute path. Discovers challenges next to this script's parent directory.
"""
from __future__ import annotations

import json
import math
import re
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
VARIANT_SEPARATOR = "@"
VARIANT_ID = re.compile(r"[a-z0-9][a-z0-9-]*")

CHALLENGES_DIR = Path(__file__).resolve().parent.parent / "challenges"
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


class ProtectedSolutionPath(ValueError):
    """A reference solution attempts to replace protected challenge content."""


STRING_METADATA_FIELDS = {
    "title",
    "type",
    "difficulty",
    "language",
    "blurb",
    "brief",
}
NUMBER_METADATA_FIELDS = {"minutes", "order"}
PATH_LIST_METADATA_FIELDS = {"readonly", "creatable"}
VARIANT_OVERRIDE_FIELDS = {
    "language",
    "runtime",
    "readonly",
    "creatable",
    "brief",
    "blurb",
    "minutes",
    "minimum_tests",
    "maximum_pristine_pass_percent",
}


def validate_documented_field_types(meta: dict[str, object]) -> None:
    for field in STRING_METADATA_FIELDS:
        if field in meta and not isinstance(meta[field], str):
            raise ValueError(f"{field} must be a string")
    for field in NUMBER_METADATA_FIELDS:
        value = meta.get(field)
        if field in meta and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{field} must be a number")
    for field in PATH_LIST_METADATA_FIELDS:
        value = meta.get(field)
        if field in meta and (
            not isinstance(value, list)
            or not all(isinstance(prefix, str) and prefix for prefix in value)
        ):
            raise ValueError(f"{field} must be an array of non-empty strings")
    minimum_tests = meta.get("minimum_tests")
    if "minimum_tests" in meta and (
        isinstance(minimum_tests, bool)
        or not isinstance(minimum_tests, int)
        or minimum_tests < 1
    ):
        raise ValueError("minimum_tests must be a positive integer")
    maximum_pass_percent = meta.get("maximum_pristine_pass_percent")
    if "maximum_pristine_pass_percent" in meta and (
        isinstance(maximum_pass_percent, bool)
        or not isinstance(maximum_pass_percent, (int, float))
        or not math.isfinite(maximum_pass_percent)
        or maximum_pass_percent <= 0
        or maximum_pass_percent > 100
    ):
        raise ValueError("maximum_pristine_pass_percent must be between 0 and 100")


def discover_slugs() -> list[str]:
    if not CHALLENGES_DIR.is_dir():
        return []
    slugs = sorted(
        child.name
        for child in CHALLENGES_DIR.iterdir()
        if child.is_dir() and (child / "challenge.json").is_file()
    )
    refs: list[str] = []
    for slug in slugs:
        refs.append(slug)
        meta = load_metadata(CHALLENGES_DIR / slug)
        variants = meta.get("variants") or {}
        if isinstance(variants, dict):
            refs.extend(f"{slug}{VARIANT_SEPARATOR}{variant}" for variant in variants)
    return refs


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
    validate_documented_field_types(meta)
    variants = meta.get("variants")
    if variants is not None:
        if not isinstance(variants, dict) or not variants:
            raise ValueError("variants must be a non-empty object")
        for variant_id, config in variants.items():
            if not isinstance(variant_id, str) or not VARIANT_ID.fullmatch(variant_id):
                raise ValueError("variant IDs must be lowercase kebab-case")
            if not isinstance(config, dict):
                raise ValueError(f"variant {variant_id} must be an object")
            unexpected = set(config) - VARIANT_OVERRIDE_FIELDS
            if unexpected:
                raise ValueError(f"variant {variant_id} has unsupported fields")
            if (
                not isinstance(config.get("language"), str)
                or not config["language"].strip()
            ):
                raise ValueError(f"variant {variant_id} requires language")
            validate_documented_field_types(config)
    return meta


def _variant_metadata(challenge: Path, variant_id: str | None) -> dict[str, object]:
    meta = load_metadata(challenge)
    if variant_id is None:
        return meta
    variants = meta.get("variants") or {}
    if not isinstance(variants, dict) or variant_id not in variants:
        raise ValueError(f"unknown variant {variant_id}")
    config = variants[variant_id]
    if not isinstance(config, dict):
        raise ValueError(f"variant {variant_id} must be an object")
    return {**meta, **config}


def runtime_config(
    challenge: Path, variant_id: str | None = None
) -> tuple[list[str], str]:
    meta = _variant_metadata(challenge, variant_id)
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
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(v, str) and v for v in command)
    ):
        raise ValueError("runtime.command must be a non-empty string array")
    requirements = runtime.get("requirements")
    if requirements is not None:
        if (
            not isinstance(requirements, str)
            or not requirements
            or Path(requirements).is_absolute()
            or ".." in Path(requirements).parts
        ):
            raise ValueError("runtime.requirements must be a safe relative path")
        repo = (
            challenge / "repo"
            if variant_id is None
            else challenge / "variants" / variant_id / "repo"
        )
        if not (repo / requirements).is_file():
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


def run_suite(
    challenge: Path, workdir: Path, variant_id: str | None = None
) -> tuple[int, str]:
    metadata_path = challenge / "challenge.json"
    if not metadata_path.is_file():
        return run_pytest(workdir)
    meta = _variant_metadata(challenge, variant_id)
    if not meta.get("runtime"):
        return run_pytest(workdir)
    command, _report = runtime_config(challenge, variant_id)
    runtime = meta.get("runtime") or {}
    python = sys.executable
    requirements_name = runtime.get("requirements")
    if requirements_name:
        # Use the same content-addressed environment contract as the platform
        # runner so validation exercises dependency-isolated challenges too.
        sys.path.insert(0, str(BACKEND_DIR))
        try:
            from environments import python_for

            repo = (
                challenge / "repo"
                if variant_id is None
                else challenge / "variants" / variant_id / "repo"
            )
            python = python_for(repo / requirements_name)
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


def test_outcome_counts(output: str) -> tuple[int, int] | None:
    """Read passed and collected counts from pytest summary or Node TAP output."""
    node_total = re.findall(r"^# tests ([0-9]+)\s*$", output, flags=re.MULTILINE)
    node_passed = re.findall(r"^# pass ([0-9]+)\s*$", output, flags=re.MULTILINE)
    if node_total and node_passed:
        return int(node_passed[-1]), int(node_total[-1])

    outcome_pattern = re.compile(
        r"(?<![\w])([0-9]+) (passed|failed|errors?|skipped|xfailed|xpassed)\b"
    )
    for line in reversed(output.splitlines()):
        outcomes = outcome_pattern.findall(line)
        if not outcomes:
            continue
        passed = sum(int(count) for count, outcome in outcomes if outcome == "passed")
        total = sum(int(count) for count, _outcome in outcomes)
        if total:
            return passed, total
    return None


def passed_test_count(output: str) -> int | None:
    counts = test_outcome_counts(output)
    return counts[0] if counts is not None else None


def quality_thresholds(meta: dict[str, object]) -> tuple[int | None, int | float | None]:
    minimum_tests = meta.get("minimum_tests")
    maximum_pass_percent = meta.get("maximum_pristine_pass_percent")
    if meta.get("difficulty") == "Medium":
        minimum_tests = minimum_tests if minimum_tests is not None else 15
        maximum_pass_percent = (
            maximum_pass_percent if maximum_pass_percent is not None else 30
        )
    return (
        minimum_tests if isinstance(minimum_tests, int) else None,
        maximum_pass_percent
        if isinstance(maximum_pass_percent, (int, float))
        else None,
    )


def validate_challenge(slug: str) -> bool:
    concept_slug, separator, variant_id = slug.partition(VARIANT_SEPARATOR)
    selected_variant = variant_id if separator else None
    challenge = CHALLENGES_DIR / concept_slug
    repo = (
        challenge / "repo"
        if selected_variant is None
        else challenge / "variants" / selected_variant / "repo"
    )
    solution = (
        challenge / "solution"
        if selected_variant is None
        else challenge / "variants" / selected_variant / "solution"
    )
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
            meta = _variant_metadata(challenge, selected_variant)
            exit_code, output = (
                run_suite(challenge, pristine)
                if selected_variant is None
                else run_suite(challenge, pristine, selected_variant)
            )
        except ValueError as exc:
            print(_fail(f"   metadata : {exc}"))
            return False
        if exit_code == 1:
            print(_ok(f"   pristine : exit {exit_code}  (expected fail)"))
            _minimum_tests, maximum_pass_percent = quality_thresholds(meta)
            if maximum_pass_percent is not None:
                counts = test_outcome_counts(output)
                if counts is None:
                    print(_fail("   starting : could not read pristine test counts"))
                    passed = False
                else:
                    passed_tests, total_tests = counts
                    actual_percent = passed_tests / total_tests * 100
                    label = (
                        f"   starting : {passed_tests}/{total_tests} pass"
                        f"  ({actual_percent:.1f}%, must be < {maximum_pass_percent:g}%)"
                    )
                    if actual_percent >= maximum_pass_percent:
                        print(_fail(label))
                        passed = False
                    else:
                        print(_ok(label))
        else:
            print(_fail(f"   pristine : exit {exit_code}  (expected test-failure exit 1)"))
            print(_tail(output))
            passed = False

        overlaid = tmpdir / "solution"
        copy_repo(repo, overlaid)
        try:
            overlay_solution(overlaid, solution, meta)
        except ProtectedSolutionPath as exc:
            print(_fail(f"   solution : protected path {exc}"))
            return False
        exit_code, output = (
            run_suite(challenge, overlaid)
            if selected_variant is None
            else run_suite(challenge, overlaid, selected_variant)
        )
        if exit_code == 0:
            print(_ok("   solution : exit 0  (expected pass)"))
            minimum_tests, _maximum_pass_percent = quality_thresholds(meta)
            if minimum_tests is not None:
                actual_tests = passed_test_count(output)
                if actual_tests is None:
                    print(_fail("   coverage : could not read solved test count"))
                    passed = False
                elif actual_tests < minimum_tests:
                    print(
                        _fail(
                            f"   coverage : {actual_tests} tests"
                            f"  (minimum {minimum_tests})"
                        )
                    )
                    passed = False
                else:
                    print(
                        _ok(
                            f"   coverage : {actual_tests} tests"
                            f"  (minimum {minimum_tests})"
                        )
                    )
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
    print(f"Validating {len(slugs)} challenge variant(s) in {CHALLENGES_DIR}")
    if not slugs:
        print("No challenges found (expected */challenge.json).")
        return 1

    failures: list[str] = []
    for slug in slugs:
        if not validate_challenge(slug):
            failures.append(slug)

    print()
    if failures:
        print(f"{len(failures)}/{len(slugs)} challenge variant(s) failed: {', '.join(failures)}")
        return 1
    print(f"{len(slugs)}/{len(slugs)} challenge variants valid (pristine fails, solution passes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
