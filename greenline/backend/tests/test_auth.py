from fastapi.testclient import TestClient

import app as api
import progress


def test_api_requires_clerk_when_secret_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(api.auth, "authenticate", lambda _request: None)

    response = TestClient(api.app).get("/api/challenges")

    assert response.status_code == 401


def test_verified_clerk_request_reaches_api(monkeypatch) -> None:
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(api.auth, "authenticate", lambda _request: {"sub": "user_123"})

    response = TestClient(api.app).get("/api/challenges")

    assert response.status_code == 200
    assert "challenges" in response.json()


def test_authenticated_progress_isolated_by_clerk_subject(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(progress, "DB_PATH", tmp_path / "progress.db")

    progress.record_run("demo", green=False, user_id="user_a")

    assert progress.get_all("user_a")["demo"]["attempts"] == 1
    assert progress.get_all("user_b") == {}
