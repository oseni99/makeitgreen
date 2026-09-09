"""Behavioral contracts for request admission and audit controls."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

import abuse_controls


def test_request_classification_uses_bounded_non_sensitive_actions() -> None:
    classified = abuse_controls.classify_request(
        "PUT",
        "/api/challenges/demo/files/private/path.py",
    )

    assert classified.action == "challenge.file.mutate"
    assert classified.slug == "demo"
    assert "private" not in classified.action
    assert (
        abuse_controls.classify_request(
            "GET", "/api/challenges/demo/runs"
        ).run
        is False
    )
    content = abuse_controls.classify_request(
        "GET", "/api/challenges/demo/files/src/app.py"
    )
    assert content.content is True
    assert content.solution is False
    assert content.action == "challenge.content.read"
    solution = abuse_controls.classify_request(
        "GET", "/api/challenges/demo/solution"
    )
    assert solution.content is True
    assert solution.solution is True
    assert solution.action == "challenge.solution.read"
    assert abuse_controls.classify_request(
        "GET", "/api/challenges/demo/runs"
    ).content is False


def test_request_body_limit_rejects_declared_oversize_before_handler() -> None:
    application = FastAPI()
    application.add_middleware(
        abuse_controls.RequestBodyLimitMiddleware,
        max_bytes=4,
    )

    @application.post("/")
    async def receive(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    client = TestClient(application)

    assert client.post("/", content=b"1234").json() == {"size": 4}
    rejected = client.post("/", content=b"12345")
    assert rejected.status_code == 413
    assert rejected.json() == {"detail": "request body too large"}


def test_request_body_limit_counts_streamed_chunks_without_content_length() -> None:
    application = FastAPI()

    async def too_large(_request, _exc):
        return JSONResponse({"detail": "request body too large"}, status_code=413)

    application.add_exception_handler(
        abuse_controls.RequestBodyTooLarge,
        too_large,
    )
    application.add_middleware(
        abuse_controls.RequestBodyLimitMiddleware,
        max_bytes=4,
    )

    @application.post("/")
    async def receive(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    rejected = TestClient(application, raise_server_exceptions=False).post(
        "/",
        content=(chunk for chunk in (b"123", b"45")),
    )

    assert rejected.status_code == 413


def test_abuse_control_policy_rejects_incoherent_run_capacity() -> None:
    with pytest.raises(ValueError):
        abuse_controls.AbuseControlPolicy(
            max_active_runs=1,
            max_active_runs_per_user=2,
        )


@pytest.mark.skipif(
    not os.environ.get("GREENLINE_TEST_DATABASE_URL"),
    reason="requires a schema-version-7 PostgreSQL integration database",
)
def test_postgres_rate_limit_and_audit_lifecycle_are_durable() -> None:
    dsn = os.environ["GREENLINE_TEST_DATABASE_URL"]
    policy = abuse_controls.AbuseControlPolicy(
        requests_per_minute=3,
        mutations_per_minute=1,
        runs_per_minute=1,
    )
    adapter = abuse_controls.PostgresAbuseControlAdapter.connect(dsn, policy)
    user_id = f"abuse-contract-{uuid4().hex}"
    try:
        admitted = adapter.begin_request(
            user_id,
            "PUT",
            "/api/challenges/demo/files/answer.py",
            "request-1",
        )
        adapter.finish_request(admitted, 200)

        with pytest.raises(abuse_controls.RateLimitExceeded):
            adapter.begin_request(
                user_id,
                "POST",
                "/api/challenges/demo/reset",
                "request-2",
            )
        with pytest.raises(abuse_controls.RateLimitExceeded):
            adapter.begin_request(
                user_id,
                "POST",
                "/api/challenges/demo/spoil",
                "request-3",
            )

        rows = adapter.list_audit_events(user_id)
        assert [row["outcome"] for row in rows] == [
            "rate_limited",
            "succeeded",
        ]
        assert rows[1]["action"] == "challenge.file.mutate"
        assert rows[1]["response_status"] == 200
    finally:
        adapter.close()


@pytest.mark.skipif(
    not os.environ.get("GREENLINE_TEST_DATABASE_URL"),
    reason="requires a schema-version-7 PostgreSQL integration database",
)
def test_postgres_blocks_bulk_cross_challenge_and_solution_reads() -> None:
    dsn = os.environ["GREENLINE_TEST_DATABASE_URL"]
    policy = abuse_controls.AbuseControlPolicy(
        requests_per_minute=20,
        mutations_per_minute=10,
        runs_per_minute=5,
        content_reads_per_minute=10,
        distinct_challenges_per_hour=2,
        solutions_per_hour=1,
    )
    adapter = abuse_controls.PostgresAbuseControlAdapter.connect(dsn, policy)
    distinct_user = f"content-distinct-{uuid4().hex}"
    solution_user = f"content-solution-{uuid4().hex}"
    try:
        adapter.begin_request(
            distinct_user, "GET", "/api/challenges/alpha", "request-1"
        )
        adapter.begin_request(
            distinct_user, "GET", "/api/challenges/beta/files/main.py", "request-2"
        )
        with pytest.raises(abuse_controls.ContentScrapeDetected) as distinct:
            adapter.begin_request(
                distinct_user, "GET", "/api/challenges/gamma", "request-3"
            )
        assert distinct.value.retry_after == 3600

        adapter.begin_request(
            solution_user, "GET", "/api/challenges/alpha/solution", "request-4"
        )
        with pytest.raises(abuse_controls.ContentScrapeDetected):
            adapter.begin_request(
                solution_user, "GET", "/api/challenges/beta/solution", "request-5"
            )

        assert adapter.list_audit_events(distinct_user)[0]["action"] == (
            "challenge.content.read"
        )
        assert adapter.list_audit_events(solution_user)[0]["action"] == (
            "challenge.solution.read"
        )
    finally:
        adapter.close()
