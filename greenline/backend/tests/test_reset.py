from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as api
import challenges as ch


@pytest.fixture
def isolated_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    challenges_dir = tmp_path / "challenges"
    workspaces_dir = tmp_path / "data" / "workspaces"
    challenge_dir = challenges_dir / "known-challenge"
    challenge_dir.mkdir(parents=True)
    (challenge_dir / "challenge.json").write_text('{"title": "Known"}')

    monkeypatch.setattr(ch, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(ch, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api.progress, "reset", lambda slug: None)
    return challenges_dir, workspaces_dir


def test_reset_unknown_challenge_returns_404(isolated_data: tuple[Path, Path]) -> None:
    response = TestClient(api.app).post("/api/challenges/missing/reset")

    assert response.status_code == 404
    assert response.json() == {"detail": "challenge not found"}


def test_reset_workspace_rejects_target_outside_workspace_root(
    isolated_data: tuple[Path, Path],
) -> None:
    _, workspaces_dir = isolated_data
    sentinel = workspaces_dir.parent / "progress.db"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("must survive")

    with pytest.raises(ch.InvalidPath):
        ch.reset_workspace("..")

    assert sentinel.read_text() == "must survive"


def test_reset_known_challenge_deletes_only_its_workspace(
    isolated_data: tuple[Path, Path],
) -> None:
    _, workspaces_dir = isolated_data
    target_file = workspaces_dir / "known-challenge" / "edited.py"
    other_file = workspaces_dir / "other-challenge" / "edited.py"
    target_file.parent.mkdir(parents=True)
    other_file.parent.mkdir(parents=True)
    target_file.write_text("edited")
    other_file.write_text("keep")

    response = TestClient(api.app).post("/api/challenges/known-challenge/reset")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert not target_file.parent.exists()
    assert other_file.read_text() == "keep"
