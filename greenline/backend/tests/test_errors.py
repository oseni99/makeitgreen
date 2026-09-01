from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as api
import challenges as ch


@pytest.fixture
def isolated_challenges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    challenges_dir = tmp_path / "challenges"
    workspaces_dir = tmp_path / "data" / "workspaces"
    challenges_dir.mkdir()

    monkeypatch.setattr(ch, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(ch, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api.progress, "get_all", lambda: {})
    return challenges_dir


def _create_challenge(challenges_dir: Path, slug: str) -> Path:
    challenge_dir = challenges_dir / slug
    (challenge_dir / "repo").mkdir(parents=True)
    (challenge_dir / "challenge.json").write_text(
        json.dumps({"title": "Test challenge"}), encoding="utf-8"
    )
    return challenge_dir


def test_malformed_metadata_returns_deterministic_json_error(
    isolated_challenges: Path,
) -> None:
    valid = _create_challenge(isolated_challenges, "valid")
    (valid / "repo" / "main.py").write_text("pass\n", encoding="utf-8")

    invalid = isolated_challenges / "invalid"
    invalid.mkdir()
    (invalid / "challenge.json").write_text('{"title":', encoding="utf-8")

    response = TestClient(api.app, raise_server_exceptions=False).get(
        "/api/challenges"
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "invalid challenge metadata"}


def test_non_utf8_repo_file_returns_deterministic_json_error(
    isolated_challenges: Path,
) -> None:
    challenge = _create_challenge(isolated_challenges, "invalid-repo-file")
    (challenge / "repo" / "main.py").write_bytes(b"print('ok')\n\xff")

    response = TestClient(api.app, raise_server_exceptions=False).get(
        "/api/challenges/invalid-repo-file/files/main.py"
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "challenge file is not valid UTF-8"}


def test_search_non_utf8_repo_file_returns_deterministic_json_error(
    isolated_challenges: Path,
) -> None:
    challenge = _create_challenge(isolated_challenges, "invalid-search-file")
    (challenge / "repo" / "main.py").write_text("needle\n", encoding="utf-8")
    (challenge / "repo" / "broken.py").write_bytes(b"needle\n\xff")

    response = TestClient(api.app, raise_server_exceptions=False).get(
        "/api/challenges/invalid-search-file/search", params={"q": "needle"}
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "challenge file is not valid UTF-8"}


def test_non_utf8_solution_file_returns_deterministic_json_error(
    isolated_challenges: Path,
) -> None:
    challenge = _create_challenge(isolated_challenges, "invalid-solution-file")
    (challenge / "repo" / "main.py").write_text("broken\n", encoding="utf-8")
    solution_dir = challenge / "solution"
    solution_dir.mkdir()
    (solution_dir / "SOLUTION.md").write_text("Fix it.\n", encoding="utf-8")
    (solution_dir / "main.py").write_bytes(b"fixed\n\xff")

    response = TestClient(api.app, raise_server_exceptions=False).get(
        "/api/challenges/invalid-solution-file/solution"
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "challenge file is not valid UTF-8"}
