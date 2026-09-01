"""Unit tests for challenge discovery, overlays, and solution assembly."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import challenges as ch


@pytest.fixture
def isolated_challenges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    challenges_dir = tmp_path / "challenges"
    workspaces_dir = tmp_path / "workspaces"
    challenges_dir.mkdir()
    monkeypatch.setattr(ch, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(ch, "WORKSPACES_DIR", workspaces_dir)
    return challenges_dir


def _write_challenge(
    challenges_dir: Path,
    slug: str,
    *,
    meta: dict | None = None,
    repo_files: dict[str, str] | None = None,
    solution_files: dict[str, str] | None = None,
) -> Path:
    challenge_dir = challenges_dir / slug
    (challenge_dir / "repo").mkdir(parents=True)
    (challenge_dir / "challenge.json").write_text(
        json.dumps(meta if meta is not None else {"title": slug}),
        encoding="utf-8",
    )
    for rel, content in (repo_files or {}).items():
        path = challenge_dir / "repo" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if solution_files is not None:
        for rel, content in solution_files.items():
            path = challenge_dir / "solution" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return challenge_dir


def test_read_file_prefers_workspace_overlay(
    isolated_challenges: Path,
) -> None:
    _write_challenge(
        isolated_challenges,
        "demo",
        repo_files={"src/app.py": "original\n"},
    )
    assert ch.read_file("demo", "src/app.py") == "original\n"

    overlay = ch.workspace_dir("demo") / "src" / "app.py"
    overlay.parent.mkdir(parents=True)
    overlay.write_text("edited overlay\n", encoding="utf-8")

    assert ch.read_file("demo", "src/app.py") == "edited overlay\n"


def test_file_tree_edited_is_true_iff_workspace_copy_exists(
    isolated_challenges: Path,
) -> None:
    _write_challenge(
        isolated_challenges,
        "demo",
        repo_files={"keep.py": "keep\n", "changed.py": "old\n"},
    )
    ws = ch.workspace_dir("demo")
    (ws / "changed.py").write_text("new\n", encoding="utf-8")
    (ws / "brand_new.py").write_text("only in workspace\n", encoding="utf-8")

    by_path = {f["path"]: f for f in ch.file_tree("demo")}

    assert by_path["keep.py"]["edited"] is False
    assert by_path["keep.py"]["new"] is False
    assert by_path["changed.py"]["edited"] is True
    assert by_path["changed.py"]["new"] is False
    assert by_path["brand_new.py"]["edited"] is True
    assert by_path["brand_new.py"]["new"] is True


def test_solution_files_assembles_writeup_and_originals(
    isolated_challenges: Path,
) -> None:
    _write_challenge(
        isolated_challenges,
        "demo",
        repo_files={"src/app.py": "broken\n", "untouched.py": "same\n"},
        solution_files={
            "SOLUTION.md": "Fix the bug.\n",
            "src/app.py": "fixed\n",
            "src/extra.py": "new file\n",
        },
    )

    result = ch.solution_files("demo")
    by_path = {f["path"]: f for f in result["files"]}

    assert result["writeup"] == "Fix the bug.\n"
    assert "SOLUTION.md" not in by_path
    assert by_path["src/app.py"] == {
        "path": "src/app.py",
        "content": "fixed\n",
        "original": "broken\n",
    }
    assert by_path["src/extra.py"] == {
        "path": "src/extra.py",
        "content": "new file\n",
        "original": "",
    }
    assert "untouched.py" not in by_path


def test_metadata_array_raises_invalid_challenge_metadata(
    isolated_challenges: Path,
) -> None:
    challenge_dir = isolated_challenges / "bad-shape"
    challenge_dir.mkdir()
    (challenge_dir / "challenge.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ch.InvalidChallengeMetadata):
        ch.load("bad-shape")


def test_metadata_extra_fields_and_missing_optional_are_ok(
    isolated_challenges: Path,
) -> None:
    _write_challenge(
        isolated_challenges,
        "sparse",
        meta={"title": "Sparse", "unknown_field": "ignored"},
        repo_files={"main.py": "pass\n"},
    )

    meta = ch.load("sparse")
    assert meta["slug"] == "sparse"
    assert meta["title"] == "Sparse"
    assert meta["unknown_field"] == "ignored"
    assert "readonly" not in meta
    assert "creatable" not in meta
    assert "minutes" not in meta


@pytest.mark.parametrize(
    "runtime",
    [
        "node",
        {"kind": "shell", "command": ["echo"]},
        {"kind": "node"},
        {"kind": "node", "command": "node --test"},
        {"kind": "python", "requirements": "../requirements.txt"},
    ],
)
def test_invalid_runtime_metadata_is_rejected(
    isolated_challenges: Path, runtime: object
) -> None:
    _write_challenge(
        isolated_challenges,
        "bad-runtime",
        meta={"title": "Bad runtime", "runtime": runtime},
    )

    with pytest.raises(ch.InvalidChallengeMetadata):
        ch.load("bad-runtime")


def test_declared_requirements_file_is_intrinsically_readonly() -> None:
    meta = {"runtime": {"kind": "python", "requirements": "requirements.txt"}}

    assert ch.is_readonly(meta, "requirements.txt") is True
