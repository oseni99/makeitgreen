import os
import signal
import time
import tracemalloc
from pathlib import Path

import pytest

import challenges
import runner


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_structured_results_report_per_test_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    (repo / "tests").mkdir(parents=True)
    workspace.mkdir()
    (repo / "lib.py").write_text("def add(a, b):\n    return a - b  # bug\n")
    (repo / "tests" / "test_lib.py").write_text(
        "import sys\n"
        "sys.path.insert(0, '..')\n"
        "from lib import add\n\n"
        "def test_passes():\n"
        "    assert True\n\n"
        "def test_fails():\n"
        "    assert add(2, 3) == 5\n"
    )
    (repo / "conftest.py").write_text("")
    monkeypatch.setattr(runner, "repo_dir", lambda slug: repo)
    monkeypatch.setattr(runner, "workspace_dir", lambda slug: workspace)

    result = runner.run_tests("structured-results")

    assert result["passed"] == 1
    assert result["failed"] == 1
    by_id = {t["id"]: t for t in result["tests"]}
    assert by_id["tests/test_lib.py::test_passes"]["outcome"] == "passed"

    failed = by_id["tests/test_lib.py::test_fails"]
    assert failed["outcome"] == "failed"
    assert failed["file"] == "tests/test_lib.py"
    assert failed["line"] is not None
    assert "assert" in failed["message"]
    # Crash location should be repo-relative, not an absolute sandbox path.
    assert failed["crash_file"] == "tests/test_lib.py"
    assert isinstance(failed["crash_line"], int)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group regression")
def test_timeout_terminates_descendant_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    child_pid_file = tmp_path / "child.pid"
    (repo / "tests").mkdir(parents=True)
    workspace.mkdir()
    (repo / "tests" / "test_hang.py").write_text(
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n\n"
        "def test_hangs():\n"
        "    child = subprocess.Popen(\n"
        "        [sys.executable, '-c', 'import time; time.sleep(30)'],\n"
        "        stdout=subprocess.DEVNULL,\n"
        "        stderr=subprocess.DEVNULL,\n"
        "    )\n"
        f"    Path({str(child_pid_file)!r}).write_text(str(child.pid))\n"
        "    time.sleep(30)\n"
    )
    monkeypatch.setattr(runner, "repo_dir", lambda slug: repo)
    monkeypatch.setattr(runner, "workspace_dir", lambda slug: workspace)
    monkeypatch.setattr(runner, "TIMEOUT_SECONDS", 0.5)

    result = runner.run_tests("timeout-regression")
    assert child_pid_file.is_file()
    child_pid = int(child_pid_file.read_text())

    try:
        deadline = time.monotonic() + 2
        while _process_exists(child_pid) and time.monotonic() < deadline:
            time.sleep(0.02)

        assert result["exit_code"] == -1
        assert "tests/test_hang.py::test_hangs" in result["output"]
        assert "TIMEOUT: test run exceeded 0.5s" in result["output"]
        assert not _process_exists(child_pid)
    finally:
        if _process_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def _tiny_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tests_src: str | None
) -> None:
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    (repo / "tests").mkdir(parents=True)
    workspace.mkdir()
    if tests_src is not None:
        (repo / "tests" / "test_mod.py").write_text(tests_src)
    monkeypatch.setattr(runner, "repo_dir", lambda slug: repo)
    monkeypatch.setattr(runner, "workspace_dir", lambda slug: workspace)


def test_all_pass_is_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _tiny_repo(
        tmp_path,
        monkeypatch,
        "def test_one():\n    assert True\n\ndef test_two():\n    assert 1 + 1 == 2\n",
    )

    result = runner.run_tests("all-pass")

    assert result["exit_code"] == 0
    assert result["green"] is True
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["skipped"] == 0


def test_all_fail_is_not_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _tiny_repo(
        tmp_path,
        monkeypatch,
        "def test_a():\n    assert False\n\ndef test_b():\n    assert 0\n",
    )

    result = runner.run_tests("all-fail")

    assert result["exit_code"] != 0
    assert result["green"] is False
    assert result["passed"] == 0
    assert result["failed"] == 2


def test_no_tests_collected_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tiny_repo(tmp_path, monkeypatch, tests_src=None)

    result = runner.run_tests("no-tests")

    assert result["exit_code"] != 0
    assert result["green"] is False
    assert result["passed"] == 0
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["skipped"] == 0
    assert result["tests"] == []


def test_stdout_and_stderr_appear_in_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tiny_repo(
        tmp_path,
        monkeypatch,
        "import sys\n\n"
        "def test_streams():\n"
        "    print('STDOUT_MARKER_GL')\n"
        "    print('STDERR_MARKER_GL', file=sys.stderr)\n"
        "    assert False\n",
    )

    result = runner.run_tests("streams")

    assert "STDOUT_MARKER_GL" in result["output"]
    assert "STDERR_MARKER_GL" in result["output"]


def test_output_truncated_to_last_20000_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tiny_repo(
        tmp_path,
        monkeypatch,
        "def test_loud():\n"
        "    print('START_UNIQUE_MARKER_GL')\n"
        "    print('P' * 25000)\n"
        "    print('END_UNIQUE_MARKER_GL')\n"
        "    assert False\n",
    )

    result = runner.run_tests("truncate")

    assert len(result["output"]) <= runner.OUTPUT_LIMIT
    assert result["output_truncated"] is True
    assert result["output"].endswith("END_UNIQUE_MARKER_GL") or (
        "END_UNIQUE_MARKER_GL" in result["output"]
    )
    assert "START_UNIQUE_MARKER_GL" not in result["output"]


def test_loud_run_retains_only_a_bounded_tail_while_streaming_all_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tiny_repo(
        tmp_path,
        monkeypatch,
        "def test_loud():\n"
        "    print('START_UNIQUE_MARKER_GL')\n"
        "    for _ in range(8000):\n"
        "        print('P' * 1000)\n"
        "    print('END_UNIQUE_MARKER_GL')\n"
        "    assert False\n",
    )
    streamed_characters = 0
    streamed_end_marker = False

    def observe(chunk: str) -> None:
        nonlocal streamed_characters, streamed_end_marker
        streamed_characters += len(chunk)
        streamed_end_marker = streamed_end_marker or "END_UNIQUE_MARKER_GL" in chunk

    tracemalloc.start()
    try:
        result = runner.run_tests("bounded-tail", observe)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert streamed_characters > 8_000_000
    assert streamed_end_marker is True
    assert len(result["output"]) <= runner.OUTPUT_LIMIT
    assert "END_UNIQUE_MARKER_GL" in result["output"]
    assert "START_UNIQUE_MARKER_GL" not in result["output"]
    assert result["output_truncated"] is True
    assert peak_bytes < 4_000_000


@pytest.mark.parametrize(
    "summary, expected",
    [
        ("2 failed, 1 passed", {"passed": 1, "failed": 2, "errors": 0}),
        ("1 error", {"passed": 0, "failed": 0, "errors": 1}),
        ("3 passed", {"passed": 3, "failed": 0, "errors": 0}),
        ("1 failed, 2 passed, 1 error", {"passed": 2, "failed": 1, "errors": 1}),
        ("2 errors, 3 passed, 1 failed", {"passed": 3, "failed": 1, "errors": 2}),
        ("# tests 6\n# pass 5\n# fail 1", {"passed": 5, "failed": 1, "errors": 0}),
    ],
)
def test_parse_counts_reads_pytest_summaries(
    summary: str, expected: dict[str, int]
) -> None:
    assert runner._parse_counts(summary) == expected


def test_run_revalidates_persisted_workspace_before_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge_root = tmp_path / "challenges" / "guarded"
    repo = challenge_root / "repo"
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "guarded"
    (repo / "tests").mkdir(parents=True)
    workspace.mkdir(parents=True)
    (challenge_root / "challenge.json").write_text(
        '{"readonly":["tests/"],"creatable":["src/"]}'
    )
    (repo / "tests" / "test_guard.py").write_text("def test_red(): assert False\n")
    # Simulate stale/tampered persisted data that bypassed the write API.
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_guard.py").write_text("def test_green(): assert True\n")
    monkeypatch.setattr(challenges, "CHALLENGES_DIR", tmp_path / "challenges")
    monkeypatch.setattr(challenges, "WORKSPACES_DIR", workspace_root)
    monkeypatch.setattr(runner, "repo_dir", challenges.repo_dir)
    monkeypatch.setattr(runner, "workspace_dir", challenges.workspace_dir)

    with pytest.raises(challenges.InvalidPath):
        runner.run_tests("guarded")


def test_stream_callback_receives_output_before_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tiny_repo(tmp_path, monkeypatch, "def test_visible():\n    assert False\n")
    chunks: list[str] = []

    result = runner.run_tests("streamed", chunks.append)

    assert result["green"] is False
    assert "test_visible" in "".join(chunks)
