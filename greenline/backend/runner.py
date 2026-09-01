"""Sandboxed-ish test execution.

Copies the challenge repo into a temp dir, overlays the user's edited files,
and runs pytest with a hard timeout. Local personal use: isolation is a temp
dir + timeout, not a container.
"""
from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import time
from pathlib import Path
from typing import Any, Callable

import challenges
import environments
from challenges import IGNORED, repo_dir, workspace_dir

TIMEOUT_SECONDS = 60
TERMINATION_GRACE_SECONDS = 1.0

# Maximum characters of failure detail forwarded to the UI per test.
MESSAGE_LIMIT = 4000

# Cap pytest stdout/stderr forwarded to the client (tail kept).
OUTPUT_LIMIT = 20_000


def _parse_counts(output: str) -> dict[str, int]:
    """Fallback for pytest text and Node's TAP summary."""
    counts = {"passed": 0, "failed": 0, "errors": 0}
    for m in re.finditer(r"(\d+) (passed|failed|error)", output):
        key = m.group(2) if m.group(2) != "error" else "errors"
        counts[key] = int(m.group(1))
    tap = {
        key: int(value)
        for key, value in re.findall(r"^# (pass|fail) (\d+)\s*$", output, re.MULTILINE)
    }
    if tap:
        counts["passed"] = tap.get("pass", 0)
        counts["failed"] = tap.get("fail", 0)
    return counts


def _relative_to_repo(path_str: str, tmpdir: Path) -> str | None:
    """Map an absolute path inside the sandbox back to a repo-relative path."""
    if not path_str:
        return None
    try:
        return Path(path_str).resolve().relative_to(tmpdir.resolve()).as_posix()
    except ValueError:
        return None


def _tests_from_report(report: dict[str, Any], tmpdir: Path) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    for t in report.get("tests", []):
        nodeid = t.get("nodeid", "")
        file = nodeid.split("::")[0] if "::" in nodeid else None
        # pytest reports 0-based item line numbers.
        lineno = t.get("lineno")
        line = lineno + 1 if isinstance(lineno, int) else None

        duration_ms = 0.0
        message = ""
        crash_file: str | None = None
        crash_line: int | None = None
        for stage_name in ("setup", "call", "teardown"):
            stage = t.get(stage_name) or {}
            duration_ms += (stage.get("duration") or 0.0) * 1000
            if stage.get("outcome") in ("failed", "error") and not message:
                crash = stage.get("crash") or {}
                message = (crash.get("message") or "")[:MESSAGE_LIMIT]
                crash_file = _relative_to_repo(crash.get("path", ""), tmpdir)
                crash_line = crash.get("lineno")
                if not message and stage.get("longrepr"):
                    message = str(stage["longrepr"])[:MESSAGE_LIMIT]

        tests.append(
            {
                "id": nodeid,
                "outcome": t.get("outcome", "unknown"),
                "duration_ms": round(duration_ms, 1),
                "file": file,
                "line": line,
                "message": message,
                "crash_file": crash_file,
                "crash_line": crash_line,
            }
        )
    return tests


def _counts_from_report(report: dict[str, Any]) -> dict[str, int]:
    summary = report.get("summary", {})
    return {
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "errors": summary.get("error", 0),
        "skipped": summary.get("skipped", 0),
    }


def _group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_timed_out_process(
    proc: subprocess.Popen[str],
) -> tuple[str, str]:
    """Terminate pytest and descendants, then collect all captured output."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

        deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
        while _group_exists(proc.pid) and time.monotonic() < deadline:
            time.sleep(0.02)

        if _group_exists(proc.pid):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    else:
        # Python's process-group controls differ on Windows. At minimum, keep
        # timeout cleanup bounded without importing POSIX-only APIs at runtime.
        proc.terminate()

    try:
        return proc.communicate(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.communicate()


def _runtime(slug: str, src: Path, tmpdir: Path, report_path: Path) -> tuple[list[str], str]:
    try:
        meta = challenges.load(slug)
    except challenges.ChallengeNotFound:
        # Runner unit tests construct an ephemeral repo without catalog data.
        meta = {}
    runtime = meta.get("runtime") or {}
    requirements_name = runtime.get("requirements")
    requirements = src / requirements_name if requirements_name else None
    if requirements is not None and not requirements.is_file():
        raise challenges.InvalidChallengeMetadata(slug)
    python = environments.python_for(requirements)
    command = runtime.get("command")
    if command is None:
        command = [
            "{python}", "-m", "pytest", "-v", "--color=no",
            "-p", "no:cacheprovider", "--json-report",
            "{json_report}", "--json-report-omit", "collectors", "keywords",
            "streams", "log",
        ]
    if not isinstance(command, list) or not command or not all(isinstance(v, str) for v in command):
        raise challenges.InvalidChallengeMetadata(slug)
    substitutions = {
        "{python}": python,
        "{repo}": str(tmpdir),
        "{json_report}": f"--json-report-file={report_path}",
    }
    default_report = "text" if runtime.get("kind") == "node" else "pytest-json"
    return [substitutions.get(part, part) for part in command], runtime.get("report", default_report)


def run_tests(slug: str, on_output: Callable[[str], None] | None = None) -> dict[str, Any]:
    src = repo_dir(slug)
    ws = workspace_dir(slug)

    with (
        tempfile.TemporaryDirectory(prefix=f"greenline-{slug}-") as tmp,
        # The report lives outside the sandboxed repo copy so code under test
        # can't trivially replace it.
        tempfile.TemporaryDirectory(prefix=f"greenline-report-{slug}-") as report_tmp,
    ):
        tmpdir = Path(tmp)
        report_path = Path(report_tmp) / "report.json"
        shutil.copytree(
            src, tmpdir, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*IGNORED),
        )
        # Overlay user edits only after revalidating persisted workspace data.
        persisted = any(path.is_file() for path in ws.rglob("*"))
        overlays = challenges.workspace_overlays(slug) if persisted else []
        for edited, rel in overlays:
            dest = tmpdir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(edited, dest)

        popen_kwargs: dict[str, Any] = {}
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        command, report_kind = _runtime(slug, src, tmpdir, report_path)
        proc = subprocess.Popen(
            command,
            cwd=tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **popen_kwargs,
        )
        chunks: list[str] = []

        def read_output() -> None:
            assert proc.stdout is not None
            for chunk in proc.stdout:
                chunks.append(chunk)
                if on_output is not None:
                    on_output(chunk)

        reader = Thread(target=read_output, daemon=True)
        reader.start()
        try:
            proc.wait(timeout=TIMEOUT_SECONDS)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            _terminate_timed_out_process(proc)
            exit_code = -1
        reader.join(timeout=TERMINATION_GRACE_SECONDS)
        output = "".join(chunks)
        if exit_code == -1:
            output += f"\n\nTIMEOUT: test run exceeded {TIMEOUT_SECONDS}s (possible deadlock or infinite loop)"

        tests: list[dict[str, Any]] = []
        counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
        if report_kind == "pytest-json" and report_path.is_file():
            try:
                report = json.loads(report_path.read_text())
                tests = _tests_from_report(report, tmpdir)
                counts = _counts_from_report(report)
            except (json.JSONDecodeError, UnicodeDecodeError):
                counts = {**_parse_counts(output), "skipped": 0}
        else:
            # Timeout or a crash before the plugin could write its report.
            counts = {**_parse_counts(output), "skipped": 0}

    truncated = len(output) > OUTPUT_LIMIT
    return {
        "exit_code": exit_code,
        "green": exit_code == 0,
        "output": output[-OUTPUT_LIMIT:],
        "output_truncated": truncated,
        "tests": tests,
        **counts,
    }
