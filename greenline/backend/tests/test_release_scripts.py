"""Behavioral contracts for immutable publication and environment promotion."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[2] / "scripts"
COMMIT = "a" * 40


def _digest(component: str, prefix: str = "source") -> str:
    return "sha256:" + hashlib.sha256(f"{prefix}:{component}".encode()).hexdigest()


def _fake_docker(tmp_path: Path) -> Path:
    executable = tmp_path / "docker"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import hashlib\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "args = sys.argv[1:]\n"
        "state_path = Path(os.environ['FAKE_REGISTRY_STATE'])\n"
        "state = json.loads(state_path.read_text()) if state_path.exists() else {}\n"
        "ref = args[-1]\n"
        "component = next(name for name in (\n"
        "    'control-plane', 'execution-worker', 'python-execution', 'node-execution'\n"
        ") if name in ref)\n"
        "source = 'sha256:' + hashlib.sha256(f'source:{component}'.encode()).hexdigest()\n"
        "previous = 'sha256:' + hashlib.sha256(f'previous:{component}'.encode()).hexdigest()\n"
        "if 'inspect' in args:\n"
        "    if ref.startswith('oci-archive:') or ':sha-' in ref:\n"
        "        if os.environ.get('FAKE_IMMUTABLE_COLLISION') == '1' and ':sha-' in ref:\n"
        "            print(previous)\n"
        "        elif ':sha-' in ref and ref not in state and 'OPERATION' not in os.environ:\n"
        "            raise SystemExit(1)\n"
        "        else:\n"
        "            print(source)\n"
        "    elif ref in state:\n"
        "        print(state[ref])\n"
        "    else:\n"
        "        print(previous)\n"
        "    raise SystemExit(0)\n"
        "if 'copy' in args:\n"
        "    source_ref = args[-2]\n"
        "    copied_digest = source_ref.rsplit('@', 1)[1] if '@sha256:' in source_ref else source\n"
        "    state[args[-1]] = copied_digest\n"
        "    state_path.write_text(json.dumps(state))\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _environment(tmp_path: Path) -> dict[str, str]:
    fake = _fake_docker(tmp_path)
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    return {
        **os.environ,
        "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
        "SKOPEO_IMAGE": "example.invalid/skopeo@sha256:" + "b" * 64,
        "REGISTRY_ROOT": "ghcr.io/acme/greenline",
        "SOURCE_TAG": f"sha-{COMMIT}",
        "AUTH_FILE": str(auth),
        "FAKE_REGISTRY_STATE": str(tmp_path / "registry.json"),
    }


def _fake_curl(tmp_path: Path) -> Path:
    executable = tmp_path / "curl"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "args = sys.argv[1:]\n"
        "output = Path(args[args.index('--output') + 1])\n"
        "counter = Path(os.environ['FAKE_CURL_COUNTER'])\n"
        "attempt = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(attempt))\n"
        f"source_sha = {COMMIT!r} if attempt > 1 else {'b' * 40!r}\n"
        "output.write_text(json.dumps({'status': 'ready', 'source_sha': source_sha}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def test_publication_refuses_to_replace_an_existing_commit_tag(
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "archives"
    output_dir = tmp_path / "output"
    archive_dir.mkdir()
    for component in (
        "control-plane",
        "execution-worker",
        "python-execution",
        "node-execution",
    ):
        (archive_dir / f"{component}.oci.tar").touch()
    environment = {
        **_environment(tmp_path),
        "ARCHIVE_DIR": str(archive_dir),
        "OUTPUT_DIR": str(output_dir),
        "FAKE_IMMUTABLE_COLLISION": "1",
    }

    result = subprocess.run(
        ["sh", str(SCRIPTS / "publish_images.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "refusing to overwrite immutable tag" in result.stderr
    assert not Path(environment["FAKE_REGISTRY_STATE"]).exists()


def test_publication_records_the_exact_archive_digests(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    output_dir = tmp_path / "output"
    archive_dir.mkdir()
    components = (
        "control-plane",
        "execution-worker",
        "python-execution",
        "node-execution",
    )
    for component in components:
        (archive_dir / f"{component}.oci.tar").touch()
    environment = {
        **_environment(tmp_path),
        "ARCHIVE_DIR": str(archive_dir),
        "OUTPUT_DIR": str(output_dir),
    }

    subprocess.run(
        ["sh", str(SCRIPTS / "publish_images.sh")],
        env=environment,
        check=True,
    )

    outputs = dict(
        line.split("=", 1)
        for line in (output_dir / "github-outputs").read_text().splitlines()
    )
    for component in components:
        assert outputs[f"{component.replace('-', '_')}_digest"] == _digest(component)
    assert outputs["registry_root"] == "ghcr.io/acme/greenline"
    registry = json.loads(Path(environment["FAKE_REGISTRY_STATE"]).read_text())
    assert set(registry) == {
        f"docker://ghcr.io/acme/greenline-{component}:sha-{COMMIT}"
        for component in components
    }


@pytest.mark.parametrize("operation", ["promote", "rollback"])
def test_environment_tag_moves_to_exact_selected_release_digests(
    tmp_path: Path, operation: str
) -> None:
    record = tmp_path / "changes.tsv"
    environment = {
        **_environment(tmp_path),
        "TARGET_TAG": "production",
        "OPERATION": operation,
        "RECORD_FILE": str(record),
    }

    subprocess.run(
        ["sh", str(SCRIPTS / "promote_images.sh")],
        env=environment,
        check=True,
    )

    changes = [line.split("\t") for line in record.read_text().splitlines()]
    assert len(changes) == 4
    for component, previous, promoted in changes:
        assert previous == _digest(component, "previous")
        assert promoted == _digest(component)


def test_release_waits_for_the_exact_ready_commit(tmp_path: Path) -> None:
    curl = _fake_curl(tmp_path)
    result = subprocess.run(
        ["sh", str(SCRIPTS / "wait_for_release.sh")],
        env={
            **os.environ,
            "PATH": f"{curl.parent}{os.pathsep}{os.environ['PATH']}",
            "FAKE_CURL_COUNTER": str(tmp_path / "curl-attempts"),
            "RELEASE_HEALTH_URL": "http://127.0.0.1:8080/health/release",
            "EXPECTED_SOURCE_SHA": COMMIT,
            "ROLLOUT_ATTEMPTS": "2",
            "ROLLOUT_INTERVAL_SECONDS": "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert f"release {COMMIT} is ready" in result.stdout


def test_automatic_rollback_restores_all_previous_digests(tmp_path: Path) -> None:
    environment = {
        **_environment(tmp_path),
        "TARGET_TAG": "production",
        "OPERATION": "promote",
        "RECORD_FILE": str(tmp_path / "promotion.tsv"),
    }
    subprocess.run(
        ["sh", str(SCRIPTS / "promote_images.sh")],
        env=environment,
        check=True,
    )
    rollback_record = tmp_path / "rollback.tsv"
    subprocess.run(
        ["sh", str(SCRIPTS / "restore_images.sh")],
        env={
            **environment,
            "PROMOTION_RECORD": environment["RECORD_FILE"],
            "ROLLBACK_RECORD": str(rollback_record),
        },
        check=True,
    )

    registry = json.loads(Path(environment["FAKE_REGISTRY_STATE"]).read_text())
    for component in (
        "control-plane",
        "execution-worker",
        "python-execution",
        "node-execution",
    ):
        target = f"docker://ghcr.io/acme/greenline-{component}:production"
        assert registry[target] == _digest(component, "previous")
    assert len(rollback_record.read_text().splitlines()) == 4


def test_automatic_rollback_preflights_the_complete_recovery_set(
    tmp_path: Path,
) -> None:
    promotion_record = tmp_path / "promotion.tsv"
    promotion_record.write_text(
        "\n".join(
            f"{component}\t{'none' if index == 0 else _digest(component, 'previous')}\t{_digest(component)}"
            for index, component in enumerate(
                (
                    "control-plane",
                    "execution-worker",
                    "python-execution",
                    "node-execution",
                )
            )
        )
        + "\n"
    )
    environment = {
        **_environment(tmp_path),
        "TARGET_TAG": "staging",
        "PROMOTION_RECORD": str(promotion_record),
        "ROLLBACK_RECORD": str(tmp_path / "rollback.tsv"),
    }

    result = subprocess.run(
        ["sh", str(SCRIPTS / "restore_images.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "no complete, valid rollback set" in result.stderr
    assert not Path(environment["FAKE_REGISTRY_STATE"]).exists()
