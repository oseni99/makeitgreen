import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

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


def test_clerk_session_verification_is_networkless_with_configured_jwt_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user_123",
            "azp": "https://app.example.com",
            "iat": now,
            "nbf": now - 1,
            "exp": now + 60,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/challenges",
            "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode("ascii"))],
            "scheme": "https",
            "server": ("app.example.com", 443),
            "client": ("127.0.0.1", 1234),
        }
    )

    def unexpected_jwks_fetch(*_args, **_kwargs):
        pytest.fail("networkless verification must not fetch Clerk JWKS")

    monkeypatch.setattr(
        "clerk_backend_api.security.verifytoken._fetch_jwks",
        unexpected_jwks_fetch,
    )

    payload = api.auth.authenticate(
        request,
        secret_key="sk_test_example",
        jwt_key=public_key,
        parties=["https://app.example.com"],
    )

    assert payload is not None
    assert payload["sub"] == "user_123"


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
    assert "auth;dur=" in response.headers["server-timing"]


def test_application_reuses_one_clerk_client_across_requests(monkeypatch) -> None:
    clients = []

    def authenticate(_request, **options):
        clients.append(options["client"])
        return {"sub": "user_123"}

    monkeypatch.setattr(api.auth, "authenticate", authenticate)
    application = api.create_application(
        {
            "GREENLINE_MODE": "local",
            "CLERK_SECRET_KEY": "sk_test_example",
            "CLERK_JWT_KEY": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        }
    )
    client = TestClient(application)

    assert client.get("/api/challenges").status_code == 200
    assert client.get("/api/challenges").status_code == 200
    assert len(clients) == 2
    assert clients[0] is clients[1]
    assert clients[0] is application.state.runtime_settings.clerk_client


def test_hosted_api_accepts_authenticated_user_without_beta_claim(monkeypatch) -> None:
    settings = SimpleNamespace(
        mode=api.RuntimeMode.HOSTED,
        clerk_secret="sk_test_example",
        clerk_jwt_key="-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        clerk_client=None,
        authorized_parties=("https://app.example.com",),
        security_events=SimpleNamespace(emit=lambda *_args, **_kwargs: None),
    )

    def request() -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/challenges",
                "query_string": b"",
                "headers": [],
                "scheme": "https",
                "server": ("app.example.com", 443),
                "client": ("127.0.0.1", 1234),
                "app": SimpleNamespace(state=SimpleNamespace(runtime_settings=settings)),
            }
        )

    reached = False

    async def call_next(_request: Request) -> JSONResponse:
        nonlocal reached
        reached = True
        return JSONResponse({"ok": True})

    monkeypatch.setattr(
        api.auth,
        "authenticate",
        lambda _request, **_kwargs: {"sub": "user_123"},
    )
    allowed = asyncio.run(api.clerk_authentication(request(), call_next))
    assert allowed.status_code == 200
    assert reached is True


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
