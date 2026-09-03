"""Behavior and security-policy contracts for ContainerExecutionAdapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import challenges
import runner


IMAGE_DIGEST = "sha256:" + "a" * 64


def _fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "fake-docker"
    record = tmp_path / "docker-calls.json"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n\n"
        "record = Path(os.environ['FAKE_DOCKER_RECORD'])\n"
        "calls = json.loads(record.read_text()) if record.exists() else []\n"
        "args = sys.argv[1:]\n"
        "calls.append(args)\n"
        "record.write_text(json.dumps(calls))\n"
        "if args[0] == 'version':\n"
        "    if os.environ.get('FAKE_DOCKER_DAEMON_DOWN') == '1':\n"
        "        raise SystemExit(1)\n"
        "    print('27.0.0')\n"
        "    raise SystemExit(0)\n"
        "if args[:2] == ['image', 'inspect']:\n"
        "    if os.environ.get('FAKE_DOCKER_IMAGE_MISSING') == '1':\n"
        "        raise SystemExit(1)\n"
        "    print('sha256:python-image-id')\n"
        "    print('sha256:node-image-id')\n"
        "    raise SystemExit(0)\n"
        "if args[0] == 'create':\n"
        "    if os.environ.get('FAKE_DOCKER_BIND_MISSING') == '1':\n"
        "        raise SystemExit(1)\n"
        "    print('fake-container-id')\n"
        "    raise SystemExit(0)\n"
        "if args[0] == 'start':\n"
        "    create = next(call for call in calls if call[0] == 'create')\n"
        "    mount = create[create.index('--mount') + 1]\n"
        "    source = next(v[4:] for v in mount.split(',') if v.startswith('src='))\n"
        "    answer = (Path(source) / 'answer.txt').read_text().strip()\n"
        "    print(f'CONTAINER_STREAM answer={answer}', flush=True)\n"
        "    time.sleep(float(os.environ.get('FAKE_DOCKER_SLEEP', '0')))\n"
        "    raise SystemExit(0 if answer == 'green' else 1)\n"
        "if args[0] == 'cp':\n"
        "    create = next(call for call in calls if call[0] == 'create')\n"
        "    mount = create[create.index('--mount') + 1]\n"
        "    source = next(v[4:] for v in mount.split(',') if v.startswith('src='))\n"
        "    green = (Path(source) / 'answer.txt').read_text().strip() == 'green'\n"
        "    outcome = 'passed' if green else 'failed'\n"
        "    report = {\n"
        "        'summary': {'passed': int(green), 'failed': int(not green)},\n"
        "        'tests': [{\n"
        "            'nodeid': 'tests/test_answer.py::test_answer',\n"
        "            'lineno': 2,\n"
        "            'outcome': outcome,\n"
        "            'call': {\n"
        "                'outcome': outcome,\n"
        "                'duration': 0.01,\n"
        "                'crash': {\n"
        "                    'path': '/workspace/tests/test_answer.py',\n"
        "                    'lineno': 3,\n"
        "                    'message': '' if green else 'assert red == green',\n"
        "                },\n"
        "            },\n"
        "        }],\n"
        "    }\n"
        "    Path(args[-1]).write_text(json.dumps(report))\n"
        "    raise SystemExit(0)\n"
        "if args[0] == 'rm':\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable, record


def _challenge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    challenge = tmp_path / "challenges" / "container-contract"
    repo = challenge / "repo"
    tests = repo / "tests"
    tests.mkdir(parents=True)
    (challenge / "challenge.json").write_text(
        json.dumps(
            {
                "title": "Container contract",
                "type": "Test",
                "difficulty": "Easy",
            }
        ),
        encoding="utf-8",
    )
    (repo / "answer.txt").write_text("red\n", encoding="utf-8")
    (tests / "test_answer.py").write_text(
        "def test_answer():\n    assert True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(challenges, "CHALLENGES_DIR", tmp_path / "challenges")
    monkeypatch.setattr(challenges, "WORKSPACES_DIR", tmp_path / "workspaces")
    monkeypatch.setattr(runner, "repo_dir", challenges.repo_dir)
    monkeypatch.setattr(runner, "workspace_dir", challenges.workspace_dir)


def _adapter(
    fake_docker: Path, *, bundle_root: Path, timeout: float = 2
) -> runner.ContainerExecutionAdapter:
    return runner.ContainerExecutionAdapter(
        runner.ContainerExecutionPolicy(
            python_image=f"greenline-python@{IMAGE_DIGEST}",
            node_image=f"greenline-node@{IMAGE_DIGEST}",
            bundle_root=str(bundle_root),
            docker_binary=str(fake_docker),
            timeout_seconds=timeout,
        )
    )


def test_hosted_run_bundle_is_readable_by_a_distinct_container_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _challenge(tmp_path, monkeypatch)
    repo = tmp_path / "challenges" / "container-contract" / "repo"
    (repo / "answer.txt").chmod(0o600)
    (repo / "tests" / "test_answer.py").chmod(0o600)
    (repo / "tests").chmod(0o700)
    repo.chmod(0o700)
    bundle_root = tmp_path / "shared-run-bundles"
    bundle_root.mkdir()

    with runner._materialized_workspace(
        runner.ChallengeRun(
            "container-contract",
            user_id="user-a",
            workspace={"answer.txt": "green\n"},
        ),
        directory=str(bundle_root),
    ) as workspace:
        paths = [workspace, *workspace.rglob("*")]
        assert all(
            (path.stat().st_mode & (0o5 if path.is_dir() else 0o4))
            == (0o5 if path.is_dir() else 0o4)
            for path in paths
        )


def test_container_readiness_requires_daemon_and_both_pinned_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_docker, record = _fake_docker(tmp_path)
    monkeypatch.setenv("FAKE_DOCKER_RECORD", str(record))
    adapter = _adapter(fake_docker, bundle_root=tmp_path)

    adapter.check_ready()

    monkeypatch.setenv("FAKE_DOCKER_IMAGE_MISSING", "1")
    with pytest.raises(runner.ExecutionUnavailable):
        adapter.check_ready()
    monkeypatch.delenv("FAKE_DOCKER_IMAGE_MISSING")
    monkeypatch.setenv("FAKE_DOCKER_DAEMON_DOWN", "1")
    with pytest.raises(runner.ExecutionUnavailable):
        adapter.check_ready()


def test_container_readiness_requires_shared_bundle_storage_visible_to_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_docker, record = _fake_docker(tmp_path)
    monkeypatch.setenv("FAKE_DOCKER_RECORD", str(record))

    missing = _adapter(fake_docker, bundle_root=tmp_path / "missing")
    with pytest.raises(runner.ExecutionUnavailable):
        missing.check_ready()

    monkeypatch.setenv("FAKE_DOCKER_BIND_MISSING", "1")
    inaccessible = _adapter(fake_docker, bundle_root=tmp_path)
    with pytest.raises(runner.ExecutionUnavailable):
        inaccessible.check_ready()


def test_container_adapter_isolates_and_normalizes_a_user_scoped_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _challenge(tmp_path, monkeypatch)
    fake_docker, record = _fake_docker(tmp_path)
    monkeypatch.setenv("FAKE_DOCKER_RECORD", str(record))
    chunks: list[str] = []

    bundle_root = tmp_path / "shared-run-bundles"
    bundle_root.mkdir()
    result = _adapter(fake_docker, bundle_root=bundle_root).execute(
        runner.ChallengeRun(
            "container-contract",
            user_id="user-a",
            workspace={"answer.txt": "green\n"},
        ),
        on_output=chunks.append,
    )

    assert result["green"] is True
    assert result["passed"] == 1
    assert result["failed"] == 0
    assert result["tests"][0]["file"] == "tests/test_answer.py"
    assert "CONTAINER_STREAM answer=green" in "".join(chunks)

    calls = json.loads(record.read_text())
    create = next(call for call in calls if call[0] == "create")
    required = {
        ("--pull", "never"),
        ("--network", "none"),
        ("--ipc", "none"),
        ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges"),
        ("--pids-limit", "128"),
        ("--memory", str(512 * 1024 * 1024)),
        ("--memory-swap", str(512 * 1024 * 1024)),
        ("--cpus", "1"),
        ("--user", "65534:65534"),
    }
    adjacent = set(zip(create, create[1:]))
    assert required <= adjacent
    assert "--read-only" in create
    assert "--init" in create
    assert "--privileged" not in create
    assert "/var/run/docker.sock" not in " ".join(create)
    assert [create[index + 1] for index, value in enumerate(create) if value == "--env"] == [
        "HOME=/tmp",
        "PYTHONDONTWRITEBYTECODE=1",
    ]
    mounts = [create[index + 1] for index, value in enumerate(create) if value == "--mount"]
    assert len(mounts) == 1
    assert "dst=/run-bundle" in mounts[0]
    assert "readonly" in mounts[0]
    assert "bind-propagation=rprivate" in mounts[0]
    source = next(value[4:] for value in mounts[0].split(",") if value.startswith("src="))
    assert Path(source).parent == bundle_root
    assert any(value.startswith("/workspace:rw,nosuid,nodev,size=") for value in create)
    container_name = create[create.index("--name") + 1]
    assert any(call[:3] == ["start", "--attach", container_name] for call in calls)
    assert any(call[0] == "cp" for call in calls)
    assert calls[-1][:2] == ["rm", "--force"]


def test_container_timeout_is_reported_and_container_is_force_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _challenge(tmp_path, monkeypatch)
    fake_docker, record = _fake_docker(tmp_path)
    monkeypatch.setenv("FAKE_DOCKER_RECORD", str(record))
    monkeypatch.setenv("FAKE_DOCKER_SLEEP", "5")

    result = _adapter(fake_docker, bundle_root=tmp_path, timeout=0.1).execute(
        runner.ChallengeRun("container-contract", workspace={})
    )

    assert result["exit_code"] == -1
    assert result["green"] is False
    assert "TIMEOUT: test run exceeded 0.1s" in result["output"]
    calls = json.loads(record.read_text())
    assert calls[-1][:2] == ["rm", "--force"]


@pytest.mark.parametrize(
    "changes",
    [
        {"python_image": "greenline-python:latest"},
        {"node_image": "greenline-node:latest"},
        {"bundle_root": "relative/run-bundles"},
        {"cpus": 0},
        {"memory_bytes": 0},
        {"pids_limit": 0},
        {"timeout_seconds": 0},
        {"user": "root"},
    ],
)
def test_container_policy_rejects_configuration_that_weakens_its_guarantees(
    changes: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "python_image": f"greenline-python@{IMAGE_DIGEST}",
        "node_image": f"greenline-node@{IMAGE_DIGEST}",
        "bundle_root": "/run-bundles",
    }
    values.update(changes)

    with pytest.raises(runner.ContainerExecutionConfigurationError):
        runner.ContainerExecutionPolicy(**values)  # type: ignore[arg-type]
