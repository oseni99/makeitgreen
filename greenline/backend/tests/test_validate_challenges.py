from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_challenges.py"
SPEC = importlib.util.spec_from_file_location("validate_challenges", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_challenges = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_challenges)


@pytest.mark.parametrize("exit_code", [-1, 2, 3, 4, 5])
def test_pristine_validator_rejects_non_test_failure_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
) -> None:
    challenges_dir = tmp_path / "challenges"
    repo = challenges_dir / "demo" / "repo"
    solution = challenges_dir / "demo" / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(exit_code, "invalid red state"), (0, "solution passed")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(validate_challenges, "run_pytest", lambda _workdir: next(results))

    assert validate_challenges.validate_challenge("demo") is False


def test_pristine_validator_accepts_normal_test_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    repo = challenges_dir / "demo" / "repo"
    solution = challenges_dir / "demo" / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(1, "one failed"), (0, "solution passed")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(validate_challenges, "run_pytest", lambda _workdir: next(results))

    assert validate_challenges.validate_challenge("demo") is True
