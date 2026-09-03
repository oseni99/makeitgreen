import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as api
import challenges
import progress
from execution_fakes import FunctionExecutionAdapter
from run_jobs import RunJobStore


@pytest.fixture
def authenticated_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    challenge = tmp_path / "challenges" / "demo"
    repo = challenge / "repo"
    repo.mkdir(parents=True)
    (challenge / "challenge.json").write_text(
        json.dumps({"title": "Demo", "type": "Test", "difficulty": "Easy"}),
        encoding="utf-8",
    )
    (repo / "main.py").write_text("original\n", encoding="utf-8")

    monkeypatch.setattr(challenges, "CHALLENGES_DIR", tmp_path / "challenges")
    monkeypatch.setattr(challenges, "WORKSPACES_DIR", tmp_path / "workspaces")
    monkeypatch.setattr(progress, "DB_PATH", tmp_path / "progress.db")
    monkeypatch.setattr(
        api.auth,
        "authenticate",
        lambda request, **_kwargs: {"sub": request.headers["x-test-user"]},
    )
    monkeypatch.setattr(
        api,
        "execution_adapter",
        FunctionExecutionAdapter(
            lambda _run, _on_output: {
                "green": False,
                "exit_code": 1,
                "output": "1 failed",
                "output_truncated": False,
                "tests": [],
                "passed": 0,
                "failed": 1,
                "errors": 0,
                "skipped": 0,
            }
        ),
    )
    return TestClient(
        api.create_application(
            {
                "GREENLINE_MODE": "local",
                "CLERK_SECRET_KEY": "sk_test_example",
            }
        )
    )


def _as(user_id: str) -> dict[str, str]:
    return {"X-Test-User": user_id}


def test_api_requires_clerk_when_secret_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(api.auth, "authenticate", lambda _request, **_kwargs: None)
    application = api.create_application(
        {
            "GREENLINE_MODE": "local",
            "CLERK_SECRET_KEY": "sk_test_example",
        }
    )

    response = TestClient(application).get("/api/challenges")

    assert response.status_code == 401


def test_verified_clerk_request_reaches_api(monkeypatch) -> None:
    monkeypatch.setattr(
        api.auth,
        "authenticate",
        lambda _request, **_kwargs: {"sub": "user_123"},
    )
    application = api.create_application(
        {
            "GREENLINE_MODE": "local",
            "CLERK_SECRET_KEY": "sk_test_example",
        }
    )

    response = TestClient(application).get("/api/challenges")

    assert response.status_code == 200
    assert "challenges" in response.json()


def test_authenticated_progress_isolated_by_clerk_subject(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(progress, "DB_PATH", tmp_path / "progress.db")

    progress.record_run("demo", green=False, user_id="user_a")

    assert progress.get_all("user_a")["demo"]["attempts"] == 1
    assert progress.get_all("user_b") == {}


def test_authenticated_workspace_operations_are_isolated_by_subject(
    authenticated_api: TestClient,
) -> None:
    client = authenticated_api

    assert client.put(
        "/api/challenges/demo/files/main.py",
        headers=_as("user_a"),
        json={"content": "marker-a\n"},
    ).status_code == 200
    assert client.get(
        "/api/challenges/demo/files/main.py", headers=_as("user_b")
    ).json()["content"] == "original\n"
    assert len(
        client.get(
            "/api/challenges/demo/search?q=marker-a", headers=_as("user_a")
        ).json()["hits"]
    ) == 1
    assert client.get(
        "/api/challenges/demo/search?q=marker-a", headers=_as("user_b")
    ).json()["hits"] == []

    client.put(
        "/api/challenges/demo/files/main.py",
        headers=_as("user_b"),
        json={"content": "marker-b\n"},
    )
    assert client.post(
        "/api/challenges/demo/reset", headers=_as("user_a")
    ).status_code == 200
    assert client.get(
        "/api/challenges/demo/files/main.py", headers=_as("user_a")
    ).json()["content"] == "original\n"
    assert client.get(
        "/api/challenges/demo/files/main.py", headers=_as("user_b")
    ).json()["content"] == "marker-b\n"


def test_authenticated_run_history_and_job_polling_are_isolated_by_subject(
    authenticated_api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = authenticated_api
    monkeypatch.setattr(api, "jobs", RunJobStore(workers=1))

    assert client.post(
        "/api/challenges/demo/run", headers=_as("user_a")
    ).status_code == 200
    assert len(
        client.get("/api/challenges/demo/runs", headers=_as("user_a")).json()[
            "runs"
        ]
    ) == 1
    assert client.get(
        "/api/challenges/demo/runs", headers=_as("user_b")
    ).json()["runs"] == []

    started = client.post(
        "/api/challenges/demo/runs", headers=_as("user_a")
    )
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    assert client.get(
        f"/api/run-jobs/{job_id}", headers=_as("user_a")
    ).status_code == 200
    assert client.get(
        f"/api/run-jobs/{job_id}", headers=_as("user_b")
    ).status_code == 404
