from pathlib import Path

import environments


def test_requirements_environment_is_cached_by_content(tmp_path, monkeypatch) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("example-package==1.0\n")
    cache = tmp_path / "cache"
    builds: list[Path] = []
    installs: list[list[str]] = []

    class FakeBuilder:
        def __init__(self, **_kwargs):
            pass

        def create(self, target):
            target = Path(target)
            python = target / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("")
            builds.append(target)

    monkeypatch.setattr(environments, "ENVIRONMENTS_DIR", cache)
    monkeypatch.setattr(environments.venv, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(
        environments.subprocess,
        "run",
        lambda command, check: installs.append(command),
    )

    first = environments.python_for(requirements)
    second = environments.python_for(requirements)

    assert first == second
    assert len(builds) == 1
    assert len(installs) == 1
    assert installs[0][-2:] == ["-r", str(requirements)]


def test_different_requirements_content_gets_different_environment(tmp_path, monkeypatch) -> None:
    requirements = tmp_path / "requirements.txt"
    monkeypatch.setattr(environments, "ENVIRONMENTS_DIR", tmp_path / "cache")

    class FakeBuilder:
        def __init__(self, **_kwargs):
            pass

        def create(self, target):
            python = Path(target) / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("")

    monkeypatch.setattr(environments.venv, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(environments.subprocess, "run", lambda *_a, **_k: None)
    requirements.write_text("alpha==1\n")
    first = environments.python_for(requirements)
    requirements.write_text("alpha==2\n")
    second = environments.python_for(requirements)

    assert first != second
