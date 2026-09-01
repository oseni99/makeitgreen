"""API contract tests for catalog, detail, run, and solution endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as api
import challenges as ch
import progress


@pytest.fixture
def isolated_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    challenges_dir = tmp_path / "challenges"
    workspaces_dir = tmp_path / "data" / "workspaces"
    challenges_dir.mkdir()

    monkeypatch.setattr(ch, "CHALLENGES_DIR", challenges_dir)
    monkeypatch.setattr(ch, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(progress, "DB_PATH", tmp_path / "progress.db")
    return challenges_dir


def _create_challenge(
    challenges_dir: Path,
    slug: str,
    *,
    meta: dict | None = None,
    repo_files: dict[str, str] | None = None,
    solution_files: dict[str, str] | None = None,
) -> Path:
    challenge_dir = challenges_dir / slug
    (challenge_dir / "repo").mkdir(parents=True)
    payload = {"title": slug, "type": "Test", "difficulty": "Easy"}
    if meta:
        payload.update(meta)
    (challenge_dir / "challenge.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    for rel, content in (repo_files or {"main.py": "pass\n"}).items():
        path = challenge_dir / "repo" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if solution_files is not None:
        for rel, content in solution_files.items():
            path = challenge_dir / "solution" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return challenge_dir


def test_catalog_lists_challenges_with_progress(isolated_api: Path) -> None:
    _create_challenge(
        isolated_api,
        "alpha",
        meta={"title": "Alpha", "order": 2, "blurb": "second"},
    )
    _create_challenge(
        isolated_api,
        "beta",
        meta={"title": "Beta", "order": 1, "blurb": "first"},
    )

    response = TestClient(api.app).get("/api/challenges")

    assert response.status_code == 200
    items = response.json()["challenges"]
    assert [item["slug"] for item in items] == ["beta", "alpha"]
    assert items[0]["title"] == "Beta"
    assert items[0]["progress"]["status"] == "todo"
    assert items[0]["progress"]["attempts"] == 0
    assert items[0]["progress"]["spoiled"] is False
    assert items[1]["progress"]["status"] == "todo"


def test_challenge_detail_success_and_unknown_404(isolated_api: Path) -> None:
    _create_challenge(
        isolated_api,
        "demo",
        meta={"title": "Demo"},
        repo_files={"src/app.py": "x = 1\n"},
    )
    client = TestClient(api.app)

    ok = client.get("/api/challenges/demo")
    assert ok.status_code == 200
    body = ok.json()
    assert body["slug"] == "demo"
    assert body["title"] == "Demo"
    assert body["progress"]["status"] == "todo"
    assert any(f["path"] == "src/app.py" for f in body["files"])

    missing = client.get("/api/challenges/does-not-exist")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "challenge not found"}


def test_solution_success_and_unknown_404(isolated_api: Path) -> None:
    _create_challenge(
        isolated_api,
        "demo",
        repo_files={"src/app.py": "broken\n"},
        solution_files={
            "SOLUTION.md": "Change it.\n",
            "src/app.py": "fixed\n",
        },
    )
    client = TestClient(api.app)

    ok = client.get("/api/challenges/demo/solution")
    assert ok.status_code == 200
    body = ok.json()
    assert body["writeup"] == "Change it.\n"
    assert body["files"][0]["path"] == "src/app.py"
    assert body["files"][0]["content"] == "fixed\n"
    assert body["files"][0]["original"] == "broken\n"

    missing = client.get("/api/challenges/does-not-exist/solution")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "solution not found"}


def test_spoil_records_flag_and_unknown_404(isolated_api: Path) -> None:
    _create_challenge(isolated_api, "demo")
    client = TestClient(api.app)

    ok = client.post("/api/challenges/demo/spoil")
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["progress"]["spoiled"] is True
    assert body["progress"]["status"] == "todo"
    assert body["progress"]["attempts"] == 0

    listed = client.get("/api/challenges/demo")
    assert listed.json()["progress"]["spoiled"] is True

    missing = client.post("/api/challenges/does-not-exist/spoil")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "challenge not found"}


def test_run_unknown_challenge_returns_404(isolated_api: Path) -> None:
    response = TestClient(api.app).post("/api/challenges/does-not-exist/run")

    assert response.status_code == 404
    assert response.json() == {"detail": "challenge not found"}


def test_async_run_start_and_poll_contract(
    isolated_api: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_challenge(isolated_api, "demo")

    class FakeJobs:
        def start(self, slug, work, *, release):
            assert slug == "demo"
            release()
            return {"job_id": "job-1", "slug": slug, "status": "queued"}

        def get(self, job_id, *, after=0):
            if job_id != "job-1":
                return None
            return {
                "job_id": job_id,
                "slug": "demo",
                "status": "running",
                "output": "collecting…\n"[after:],
                "next_offset": len("collecting…\n"),
                "output_truncated": False,
            }

    monkeypatch.setattr(api, "jobs", FakeJobs())
    client = TestClient(api.app)

    started = client.post(
        "/api/challenges/demo/runs", json={"session_elapsed_ms": 1200}
    )
    assert started.status_code == 202
    assert started.json() == {
        "job_id": "job-1",
        "slug": "demo",
        "status": "queued",
    }

    polled = client.get("/api/run-jobs/job-1?after=0")
    assert polled.status_code == 200
    assert polled.json()["output"] == "collecting…\n"
    assert client.get("/api/run-jobs/missing").status_code == 404


def test_run_passes_start_time_and_truncation_state_to_history(
    isolated_api: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_challenge(isolated_api, "demo")
    captured: dict = {}

    monkeypatch.setattr(
        api.runner,
        "run_tests",
        lambda slug: {
            "green": False,
            "exit_code": 1,
            "output": "tail",
            "output_truncated": True,
            "tests": [],
            "passed": 0,
            "failed": 1,
            "errors": 0,
            "skipped": 0,
        },
    )

    def record_run(slug: str, **kwargs) -> dict:
        captured.update(kwargs)
        return {"id": 1, "slug": slug, "started_at": kwargs["started_at"]}

    monkeypatch.setattr(api.progress, "record_run", record_run)

    response = TestClient(api.app).post("/api/challenges/demo/run")

    assert response.status_code == 200
    assert captured["started_at"]
    assert captured["output_truncated"] is True


def test_run_success_against_tiny_failing_challenge(isolated_api: Path) -> None:
    _create_challenge(
        isolated_api,
        "tiny-red",
        repo_files={
            "tests/test_tiny.py": "def test_still_broken():\n    assert False\n"
        },
    )

    response = TestClient(api.app).post("/api/challenges/tiny-red/run")

    assert response.status_code == 200
    body = response.json()
    assert body["green"] is False
    assert body["exit_code"] != 0
    assert body["failed"] == 1
    assert body["passed"] == 0
    assert "run" in body
    assert "duration_ms" in body
    assert "output" in body
    assert isinstance(body["tests"], list)
    assert len(body["tests"]) == 1
    assert body["tests"][0]["outcome"] == "failed"
