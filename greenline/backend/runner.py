"""Challenge Run execution Interface and execution Adapters.

Both Adapters copy the challenge repo into an ephemeral workspace and overlay
the learner's edits. Local Mode runs the declared command on the host. The
container Adapter runs it with an explicit resource and isolation policy.
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
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Thread
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol, TypedDict

import challenges
import environments
from challenges import IGNORED, repo_dir, workspace_dir

TIMEOUT_SECONDS = 60
TERMINATION_GRACE_SECONDS = 1.0
READINESS_TIMEOUT_SECONDS = 2.0

# Maximum characters of failure detail forwarded to the UI per test.
MESSAGE_LIMIT = 4000

# Cap pytest stdout/stderr forwarded to the client (tail kept).
OUTPUT_LIMIT = 20_000

OutputCallback = Callable[[str], None]


@dataclass(frozen=True)
class ChallengeRun:
    slug: str
    user_id: str | None = None
    workspace: Mapping[str, str] | None = None


class ChallengeRunResult(TypedDict):
    exit_code: int
    green: bool
    output: str
    output_truncated: bool
    tests: list[dict[str, Any]]
    passed: int
    failed: int
    errors: int
    skipped: int


class ExecutionAdapter(Protocol):
    def check_ready(self) -> None: ...

    def execute(
        self,
        run: ChallengeRun,
        *,
        on_output: OutputCallback | None = None,
    ) -> ChallengeRunResult: ...


class ContainerExecutionConfigurationError(ValueError):
    """The container Adapter cannot provide its promised isolation policy."""


class UnsupportedContainerRuntime(RuntimeError):
    """A Challenge Run needs dependencies absent from the configured image."""


_IMAGE_DIGEST = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ContainerExecutionPolicy:
    """Trusted configuration for isolated Challenge Runs.

    Image digests are mandatory so a Hosted Mode deployment cannot silently
    execute a different toolchain after a mutable tag changes.
    """

    python_image: str
    node_image: str
    bundle_root: str
    docker_binary: str = "docker"
    cpus: float = 1.0
    memory_bytes: int = 512 * 1024 * 1024
    pids_limit: int = 128
    tmpfs_bytes: int = 64 * 1024 * 1024
    timeout_seconds: float = TIMEOUT_SECONDS
    user: str = "65534:65534"

    def __post_init__(self) -> None:
        if not _IMAGE_DIGEST.fullmatch(self.python_image):
            raise ContainerExecutionConfigurationError(
                "python_image must be pinned by sha256 digest"
            )
        if not _IMAGE_DIGEST.fullmatch(self.node_image):
            raise ContainerExecutionConfigurationError(
                "node_image must be pinned by sha256 digest"
            )
        if not Path(self.bundle_root).is_absolute():
            raise ContainerExecutionConfigurationError(
                "bundle_root must be an absolute shared path"
            )
        if not self.docker_binary or "\x00" in self.docker_binary:
            raise ContainerExecutionConfigurationError("docker_binary is invalid")
        if self.cpus <= 0:
            raise ContainerExecutionConfigurationError("cpus must be positive")
        for name in ("memory_bytes", "pids_limit", "tmpfs_bytes"):
            if getattr(self, name) <= 0:
                raise ContainerExecutionConfigurationError(f"{name} must be positive")
        if self.timeout_seconds <= 0:
            raise ContainerExecutionConfigurationError(
                "timeout_seconds must be positive"
            )
        if not re.fullmatch(r"\d+:\d+", self.user):
            raise ContainerExecutionConfigurationError(
                "user must be a numeric uid:gid"
            )


class _OutputTail:
    """Retain at most ``limit`` characters while accepting a full stream."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._chunks: deque[str] = deque()
        self._length = 0
        self.truncated = False

    def append(self, chunk: str) -> None:
        if not chunk:
            return
        if self._limit <= 0:
            self.truncated = True
            return

        self._chunks.append(chunk)
        self._length += len(chunk)
        overflow = self._length - self._limit
        if overflow <= 0:
            return

        self.truncated = True
        while self._chunks and overflow >= len(self._chunks[0]):
            removed = self._chunks.popleft()
            removed_length = len(removed)
            self._length -= removed_length
            overflow -= removed_length
        if overflow:
            self._chunks[0] = self._chunks[0][overflow:]
            self._length -= overflow

    def text(self) -> str:
        return "".join(self._chunks)


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
    path = Path(path_str)
    for root in (tmpdir.resolve(), Path("/workspace")):
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
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


def _runtime_metadata(slug: str) -> dict[str, Any]:
    try:
        meta = challenges.load(slug)
    except challenges.ChallengeNotFound:
        # Runner unit tests construct an ephemeral repo without catalog data.
        meta = {}
    return meta.get("runtime") or {}


def _runtime_command(
    slug: str,
    runtime: dict[str, Any],
    *,
    python: str,
    repo: str,
    report_path: str,
) -> tuple[list[str], str]:
    command = runtime.get("command")
    if command is None:
        command = [
            "{python}", "-m", "pytest", "-v", "--color=no",
            "-p", "no:cacheprovider", "--json-report",
            "{json_report}", "--json-report-omit", "collectors", "keywords",
            "streams", "log",
        ]
    if not isinstance(command, list) or not command or not all(
        isinstance(value, str) for value in command
    ):
        raise challenges.InvalidChallengeMetadata(slug)
    substitutions = {
        "{python}": python,
        "{repo}": repo,
        "{json_report}": f"--json-report-file={report_path}",
    }
    default_report = "text" if runtime.get("kind") == "node" else "pytest-json"
    return (
        [substitutions.get(part, part) for part in command],
        runtime.get("report", default_report),
    )


def _runtime(slug: str, src: Path, tmpdir: Path, report_path: Path) -> tuple[list[str], str]:
    runtime = _runtime_metadata(slug)
    requirements_name = runtime.get("requirements")
    requirements = src / requirements_name if requirements_name else None
    if requirements is not None and not requirements.is_file():
        raise challenges.InvalidChallengeMetadata(slug)
    python = environments.python_for(requirements)
    return _runtime_command(
        slug,
        runtime,
        python=python,
        repo=str(tmpdir),
        report_path=str(report_path),
    )


def _make_run_bundle_readable(path: Path) -> None:
    """Grant the separate execution UID read/traverse access to a staged bundle."""
    paths = [path, *path.rglob("*")]
    for candidate in paths:
        required = 0o5 if candidate.is_dir() else 0o4
        candidate.chmod(candidate.stat().st_mode | required)


@contextmanager
def _materialized_workspace(
    run: ChallengeRun, *, directory: str | None = None
) -> Iterator[Path]:
    """Yield one validated, user-scoped snapshot for a Challenge Run."""
    src = repo_dir(run.slug)
    with tempfile.TemporaryDirectory(
        prefix=f"greenline-{run.slug}-", dir=directory
    ) as tmp:
        tmpdir = Path(tmp)
        shutil.copytree(
            src,
            tmpdir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*IGNORED),
        )
        if run.workspace is not None:
            meta = challenges.load(run.slug)
            requirements = (meta.get("runtime") or {}).get("requirements")
            for relative, content in run.workspace.items():
                repo_file, canonical = challenges._safe_relpath(src, relative)
                if (
                    canonical != relative
                    or any(part in IGNORED for part in Path(relative).parts)
                    or challenges.is_readonly(meta, canonical)
                    or canonical == requirements
                    or (
                        not repo_file.is_file()
                        and not challenges.is_creatable(meta, canonical)
                    )
                ):
                    raise challenges.InvalidPath(relative)
                destination = tmpdir / canonical
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
        else:
            ws = (
                workspace_dir(run.slug)
                if run.user_id is None
                else workspace_dir(run.slug, run.user_id)
            )
            persisted = any(path.is_file() for path in ws.rglob("*"))
            if not persisted:
                if directory is not None:
                    _make_run_bundle_readable(tmpdir)
                yield tmpdir
                return
            overlays = (
                challenges.workspace_overlays(run.slug)
                if run.user_id is None
                else challenges.workspace_overlays(run.slug, run.user_id)
            )
            for edited, rel in overlays:
                dest = tmpdir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(edited, dest)
        if directory is not None:
            # Hosted execution runs under a different numeric UID than the
            # worker that stages this read-only bind mount.
            _make_run_bundle_readable(tmpdir)
        yield tmpdir


def _process_group_options() -> dict[str, Any]:
    if os.name == "posix":
        return {"start_new_session": True}
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {}


def _capture_process(
    proc: subprocess.Popen[str],
    *,
    timeout_seconds: float,
    on_output: OutputCallback | None,
) -> tuple[int, _OutputTail]:
    output_tail = _OutputTail(OUTPUT_LIMIT)

    def read_output() -> None:
        assert proc.stdout is not None
        for chunk in proc.stdout:
            output_tail.append(chunk)
            if on_output is not None:
                on_output(chunk)

    reader = Thread(target=read_output, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout_seconds)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        _terminate_timed_out_process(proc)
        exit_code = -1
    reader.join(timeout=TERMINATION_GRACE_SECONDS)
    if exit_code == -1:
        output_tail.append(
            f"\n\nTIMEOUT: test run exceeded {timeout_seconds:g}s "
            "(possible deadlock or infinite loop)"
        )
    return exit_code, output_tail


def _normalized_result(
    *,
    exit_code: int,
    output_tail: _OutputTail,
    report_kind: str,
    report_path: Path,
    workspace: Path,
) -> ChallengeRunResult:
    output = output_tail.text()
    tests: list[dict[str, Any]] = []
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if report_kind == "pytest-json" and report_path.is_file():
        try:
            report = json.loads(report_path.read_text())
            tests = _tests_from_report(report, workspace)
            counts = _counts_from_report(report)
        except (json.JSONDecodeError, UnicodeDecodeError):
            counts = {**_parse_counts(output), "skipped": 0}
    else:
        counts = {**_parse_counts(output), "skipped": 0}
    return {
        "exit_code": exit_code,
        "green": exit_code == 0,
        "output": output,
        "output_truncated": output_tail.truncated,
        "tests": tests,
        **counts,
    }


def _execute_local(
    slug: str,
    on_output: OutputCallback | None = None,
    user_id: str | None = None,
    workspace: Mapping[str, str] | None = None,
) -> ChallengeRunResult:
    run = ChallengeRun(slug=slug, user_id=user_id, workspace=workspace)
    src = repo_dir(slug)
    with (
        _materialized_workspace(run) as tmpdir,
        # The report lives outside the sandboxed repo copy so code under test
        # can't trivially replace it.
        tempfile.TemporaryDirectory(prefix=f"greenline-report-{slug}-") as report_tmp,
    ):
        report_path = Path(report_tmp) / "report.json"
        command, report_kind = _runtime(slug, src, tmpdir, report_path)
        proc = subprocess.Popen(
            command,
            cwd=tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **_process_group_options(),
        )
        exit_code, output_tail = _capture_process(
            proc,
            timeout_seconds=TIMEOUT_SECONDS,
            on_output=on_output,
        )
        return _normalized_result(
            exit_code=exit_code,
            output_tail=output_tail,
            report_kind=report_kind,
            report_path=report_path,
            workspace=tmpdir,
        )


class LocalSubprocessAdapter:
    """Execute trusted Local Mode Challenge Runs as host subprocesses."""

    def check_ready(self) -> None:
        return None

    def execute(
        self,
        run: ChallengeRun,
        *,
        on_output: OutputCallback | None = None,
    ) -> ChallengeRunResult:
        return _execute_local(run.slug, on_output, run.user_id, run.workspace)


class ExecutionUnavailable(RuntimeError):
    """The configured execution infrastructure could not run a challenge."""


class DisabledExecutionAdapter:
    """A fail-closed placeholder for processes without execution authority."""

    def check_ready(self) -> None:
        return None

    def execute(
        self,
        run: ChallengeRun,
        *,
        on_output: OutputCallback | None = None,
    ) -> ChallengeRunResult:
        raise ExecutionUnavailable("this process has no execution authority")


@dataclass(frozen=True)
class ContainerExecutionAdapter:
    """Execute Challenge Runs in fresh, resource-limited Docker containers."""

    policy: ContainerExecutionPolicy

    def check_ready(self) -> None:
        """Verify images and prove the daemon can see staged Run Bundles."""
        version = self._docker(
            "version",
            "--format",
            "{{.Server.Version}}",
            timeout=READINESS_TIMEOUT_SECONDS,
        )
        if version.returncode != 0 or not version.stdout.strip():
            raise ExecutionUnavailable("container execution is unavailable")
        images = self._docker(
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            self.policy.python_image,
            self.policy.node_image,
            timeout=READINESS_TIMEOUT_SECONDS,
        )
        inspected = [line for line in images.stdout.splitlines() if line.strip()]
        if images.returncode != 0 or len(inspected) != 2:
            raise ExecutionUnavailable("container execution images are unavailable")
        bundle_root = Path(self.policy.bundle_root)
        try:
            with tempfile.TemporaryDirectory(
                prefix="greenline-ready-", dir=bundle_root
            ) as probe:
                name = f"greenline-ready-{uuid.uuid4().hex}"
                created = self._docker(
                    "create",
                    "--pull", "never",
                    "--name", name,
                    "--label", "io.makeitgreen.readiness=true",
                    "--network", "none",
                    "--read-only",
                    "--mount", f"type=bind,src={probe},dst=/probe,readonly",
                    self.policy.python_image,
                    "/bin/true",
                )
                try:
                    if created.returncode != 0:
                        raise ExecutionUnavailable(
                            "Run Bundle storage is not visible to the container daemon"
                        )
                finally:
                    self._remove(name)
        except OSError as exc:
            raise ExecutionUnavailable("Run Bundle storage is unavailable") from exc

    def _container_command(
        self,
        *,
        name: str,
        workspace: Path,
        image: str,
        command: list[str],
    ) -> list[str]:
        policy = self.policy
        uid, gid = policy.user.split(":", 1)
        return [
            policy.docker_binary,
            "create",
            "--pull", "never",
            "--name", name,
            "--label", "io.makeitgreen.challenge-run=true",
            "--network", "none",
            "--ipc", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", str(policy.pids_limit),
            "--memory", str(policy.memory_bytes),
            "--memory-swap", str(policy.memory_bytes),
            "--cpus", f"{policy.cpus:g}",
            "--ulimit", "nofile=1024:1024",
            "--init",
            "--user", policy.user,
            "--workdir", "/workspace",
            "--env", "HOME=/tmp",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--mount",
            (
                f"type=bind,src={workspace},dst=/run-bundle,readonly,"
                "bind-propagation=rprivate"
            ),
            "--tmpfs",
            (
                f"/workspace:rw,nosuid,nodev,size={policy.tmpfs_bytes},"
                f"uid={uid},gid={gid},mode=0700"
            ),
            "--tmpfs",
            (
                f"/tmp:rw,nosuid,nodev,size={policy.tmpfs_bytes},"
                f"uid={uid},gid={gid},mode=0700"
            ),
            "--tmpfs",
            (
                "/greenline-report:rw,nosuid,nodev,size=16777216,"
                f"uid={uid},gid={gid},mode=0700"
            ),
            image,
            "/bin/sh",
            "-c",
            'cp -R /run-bundle/. /workspace && exec "$@"',
            "greenline-init",
            *command,
        ]

    def _docker(
        self,
        *arguments: str,
        check: bool = False,
        timeout: float = 10,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.policy.docker_binary, *arguments],
                check=check,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise ExecutionUnavailable("container execution is unavailable") from exc

    def _remove(self, name: str) -> None:
        try:
            self._docker("rm", "--force", name)
        except ExecutionUnavailable:
            # The run has already failed. Cleanup is best-effort here; the
            # unique name and operational label make orphan reconciliation safe.
            pass

    def execute(
        self,
        run: ChallengeRun,
        *,
        on_output: OutputCallback | None = None,
    ) -> ChallengeRunResult:
        if run.workspace is None:
            raise ExecutionUnavailable(
                "container execution requires a durable workspace snapshot"
            )
        runtime = _runtime_metadata(run.slug)
        if runtime.get("requirements") is not None:
            raise UnsupportedContainerRuntime(
                "container images must include challenge dependencies at build time"
            )
        kind = runtime.get("kind", "python")
        image = self.policy.node_image if kind == "node" else self.policy.python_image
        command, report_kind = _runtime_command(
            run.slug,
            runtime,
            python="python",
            repo="/workspace",
            report_path="/greenline-report/report.json",
        )
        name = f"greenline-run-{uuid.uuid4().hex}"

        with (
            _materialized_workspace(
                run, directory=self.policy.bundle_root
            ) as workspace,
            tempfile.TemporaryDirectory(prefix=f"greenline-report-{run.slug}-") as report_tmp,
        ):
            create = self._container_command(
                name=name,
                workspace=workspace,
                image=image,
                command=command,
            )
            try:
                try:
                    created = subprocess.run(
                        create,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                except (FileNotFoundError, subprocess.SubprocessError) as exc:
                    raise ExecutionUnavailable(
                        "container execution is unavailable"
                    ) from exc
                if created.returncode != 0:
                    raise ExecutionUnavailable("container creation failed")

                try:
                    proc = subprocess.Popen(
                        [self.policy.docker_binary, "start", "--attach", name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        **_process_group_options(),
                    )
                except OSError as exc:
                    raise ExecutionUnavailable("container start failed") from exc
                exit_code, output_tail = _capture_process(
                    proc,
                    timeout_seconds=self.policy.timeout_seconds,
                    on_output=on_output,
                )
                report_path = Path(report_tmp) / "report.json"
                if exit_code != -1 and report_kind == "pytest-json":
                    self._docker(
                        "cp",
                        f"{name}:/greenline-report/report.json",
                        str(report_path),
                    )
                return _normalized_result(
                    exit_code=exit_code,
                    output_tail=output_tail,
                    report_kind=report_kind,
                    report_path=report_path,
                    workspace=workspace,
                )
            finally:
                self._remove(name)
