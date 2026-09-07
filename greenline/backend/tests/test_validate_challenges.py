from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_challenges.py"
SPEC = importlib.util.spec_from_file_location("validate_challenges", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_challenges = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_challenges)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("minutes", "30"),
        ("minimum_tests", 0),
        ("minimum_tests", 14.5),
        ("minimum_tests", "15"),
        ("maximum_pristine_pass_percent", 0),
        ("maximum_pristine_pass_percent", 101),
        ("maximum_pristine_pass_percent", "30"),
        ("readonly", "tests/"),
        ("readonly", ["tests/", 1]),
        ("creatable", {"src/": True}),
    ],
)
def test_validator_rejects_malformed_documented_metadata_fields(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    challenge = tmp_path / "demo"
    challenge.mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps({"title": "Demo", field: value}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=field):
        validate_challenges.load_metadata(challenge)


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


def test_validator_rejects_solution_below_declared_test_minimum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps({"difficulty": "Easy", "minimum_tests": 15})
    )
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(1, "1 failed, 13 passed"), (0, "14 passed in 0.01s")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(
        validate_challenges,
        "run_suite",
        lambda _challenge, _workdir: next(results),
    )

    assert validate_challenges.validate_challenge("demo") is False


def test_validator_accepts_solution_at_declared_test_minimum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps({"difficulty": "Easy", "minimum_tests": 15})
    )
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(1, "1 failed, 14 passed"), (0, "15 passed in 0.01s")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(
        validate_challenges,
        "run_suite",
        lambda _challenge, _workdir: next(results),
    )

    assert validate_challenges.validate_challenge("demo") is True


def test_validator_rejects_pristine_suite_at_declared_pass_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps({"maximum_pristine_pass_percent": 30})
    )
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(1, "7 failed, 3 passed in 0.01s"), (0, "10 passed in 0.01s")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(
        validate_challenges,
        "run_suite",
        lambda _challenge, _workdir: next(results),
    )

    assert validate_challenges.validate_challenge("demo") is False


def test_validator_accepts_pristine_suite_below_declared_pass_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps({"maximum_pristine_pass_percent": 30})
    )
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(1, "8 failed, 2 passed in 0.01s"), (0, "10 passed in 0.01s")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(
        validate_challenges,
        "run_suite",
        lambda _challenge, _workdir: next(results),
    )

    assert validate_challenges.validate_challenge("demo") is True


def test_validator_rejects_entirely_red_pristine_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps({"difficulty": "Medium"})
    )
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(1, "15 failed in 0.01s"), (0, "15 passed in 0.01s")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(
        validate_challenges,
        "run_suite",
        lambda _challenge, _workdir: next(results),
    )

    assert validate_challenges.validate_challenge("demo") is False


def test_medium_challenges_inherit_catalog_quality_thresholds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(json.dumps({"difficulty": "Medium"}))
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")

    results = iter([(1, "10 failed, 5 passed in 0.01s"), (0, "15 passed in 0.01s")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(
        validate_challenges,
        "run_suite",
        lambda _challenge, _workdir: next(results),
    )

    assert validate_challenges.validate_challenge("demo") is False


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("13 failed, 5 passed, 1 warning in 0.19s", (5, 18)),
        ("# tests 18\n# pass 5\n# fail 13\n", (5, 18)),
    ],
)
def test_validator_reads_pristine_counts_from_supported_runtimes(
    output: str,
    expected: tuple[int, int],
) -> None:
    assert validate_challenges.test_outcome_counts(output) == expected


def test_validator_rejects_solution_that_replaces_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo_tests = challenge / "repo" / "tests"
    solution_tests = challenge / "solution" / "tests"
    repo_tests.mkdir(parents=True)
    solution_tests.mkdir(parents=True)
    (repo_tests / "test_demo.py").write_text("def test_demo(): assert False\n")
    (solution_tests / "test_demo.py").write_text("def test_demo(): assert True\n")

    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)

    assert validate_challenges.validate_challenge("demo") is False


def test_validator_rejects_solution_that_adds_nested_conftest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo_specs = challenge / "repo" / "specs"
    solution_specs = challenge / "solution" / "specs"
    repo_specs.mkdir(parents=True)
    solution_specs.mkdir(parents=True)
    (challenge / "challenge.json").write_text(json.dumps({"readonly": []}))
    (repo_specs / "test_demo.py").write_text("def test_demo(): assert False\n")
    (solution_specs / "conftest.py").write_text(
        "import pytest\n"
        "def pytest_collection_modifyitems(items):\n"
        "    for item in items:\n"
        "        item.add_marker(pytest.mark.skip(reason='hidden by solution'))\n"
    )

    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)

    assert validate_challenges.validate_challenge("demo") is False


@pytest.mark.parametrize(
    "config_name",
    ["pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg"],
)
def test_validator_rejects_solution_that_replaces_root_pytest_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_name: str,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(json.dumps({"readonly": []}))
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")
    (solution / config_name).write_text("replacement grading configuration\n")

    results = iter([(1, "one failed"), (0, "solution passed")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(validate_challenges, "run_pytest", lambda _workdir: next(results))

    assert validate_challenges.validate_challenge("demo") is False


def test_validator_rejects_solution_under_declared_readonly_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution" / "fixtures"
    repo.mkdir(parents=True)
    solution.mkdir(parents=True)
    (challenge / "challenge.json").write_text(json.dumps({"readonly": ["fixtures/"]}))
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")
    (solution / "grading.json").write_text("{}\n")

    results = iter([(1, "one failed"), (0, "solution passed")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(validate_challenges, "run_pytest", lambda _workdir: next(results))

    assert validate_challenges.validate_challenge("demo") is False


def test_validator_rejects_solution_that_replaces_runtime_requirements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    repo = challenge / "repo"
    solution = challenge / "solution"
    repo.mkdir(parents=True)
    solution.mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps(
            {
                "readonly": [],
                "runtime": {
                    "kind": "python",
                    "requirements": "requirements.txt",
                },
            }
        )
    )
    (repo / "requirements.txt").write_text("pytest==8.*\n")
    (repo / "test_demo.py").write_text("def test_demo(): assert False\n")
    (solution / "requirements.txt").write_text("pytest==7.*\n")

    results = iter([(1, "one failed"), (0, "solution passed")])
    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(validate_challenges, "run_suite", lambda _challenge, _workdir: next(results))

    assert validate_challenges.validate_challenge("demo") is False


def test_validator_rejects_empty_runtime_requirements(tmp_path: Path) -> None:
    challenge = tmp_path / "demo"
    (challenge / "repo").mkdir(parents=True)
    (challenge / "challenge.json").write_text(
        json.dumps({"runtime": {"kind": "python", "requirements": ""}})
    )

    with pytest.raises(ValueError, match="requirements"):
        validate_challenges.runtime_config(challenge)


def test_validator_discovers_and_validates_language_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenges_dir = tmp_path / "challenges"
    challenge = challenges_dir / "demo"
    variant = challenge / "variants" / "javascript"
    (challenge / "repo").mkdir(parents=True)
    (challenge / "solution").mkdir()
    (variant / "repo").mkdir(parents=True)
    (variant / "solution").mkdir()
    (challenge / "challenge.json").write_text(
        json.dumps(
            {
                "language": "Python",
                "variants": {
                    "javascript": {
                        "language": "JavaScript",
                        "runtime": {
                            "kind": "node",
                            "command": ["node", "--test"],
                        },
                    }
                },
            }
        )
    )
    (variant / "repo" / "main.js").write_text("broken\n")
    (variant / "solution" / "main.js").write_text("fixed\n")

    calls: list[tuple[Path, str | None]] = []

    def fake_run_suite(
        _challenge: Path,
        workdir: Path,
        variant_id: str | None = None,
    ) -> tuple[int, str]:
        calls.append((workdir, variant_id))
        content = (workdir / "main.js").read_text()
        return (0 if content == "fixed\n" else 1, "")

    monkeypatch.setattr(validate_challenges, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(validate_challenges, "run_suite", fake_run_suite)

    assert validate_challenges.discover_slugs() == [
        "demo",
        "demo@javascript",
    ]
    assert validate_challenges.validate_challenge("demo@javascript") is True
    assert [variant_id for _, variant_id in calls] == ["javascript", "javascript"]
