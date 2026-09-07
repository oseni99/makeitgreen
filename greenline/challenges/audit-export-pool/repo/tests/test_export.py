"""Connection and transaction lifecycle contract for audit exports."""

import pytest

from audit_export.errors import AccessDenied, ClientCancelled, QueryFailed
from audit_export.pool import ConnectionPool
from audit_export.service import AuditExportService


def test_success_commits_before_release_and_preserves_order() -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    assert service.export("project-a", {"project-a"}) == [
        {"id": 1, "action": "project.created"},
        {"id": 2, "action": "member.invited"},
        {"id": 3, "action": "deployment.created"},
    ]
    assert pool.available == 4
    assert pool.checked_out == 0
    assert pool.events == [
        (0, "acquire"),
        (0, "begin"),
        (0, "query"),
        (0, "commit"),
        (0, "release"),
    ]


@pytest.mark.parametrize("attempts", [1, 2, 4, 6])
def test_repeated_access_denials_do_not_exhaust_pool(attempts: int) -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    for _ in range(attempts):
        with pytest.raises(AccessDenied):
            service.export("project-private", {"project-a"})

    assert pool.available == 4
    assert pool.checked_out == 0
    assert all(connection.state == "idle" for connection in pool.connections)


@pytest.mark.parametrize("attempts", [1, 2, 4])
def test_query_failure_rolls_back_before_release(attempts: int) -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    for _ in range(attempts):
        with pytest.raises(QueryFailed, match="statement failed"):
            service.export("project-query-error", {"project-query-error"})

    assert pool.events[-2:] == [(0, "rollback"), (0, "release")]
    assert pool.available == 4
    assert all(connection.state == "idle" for connection in pool.connections)


@pytest.mark.parametrize("cancel_after", [1, 2, 3])
def test_client_cancellation_rolls_back_and_returns_connection(
    cancel_after: int,
) -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    with pytest.raises(ClientCancelled, match=f"after {cancel_after} rows"):
        service.export("project-a", {"project-a"}, cancel_after=cancel_after)

    assert pool.events[-2:] == [(0, "rollback"), (0, "release")]
    assert pool.available == 4
    assert pool.connections[0].state == "idle"


@pytest.mark.parametrize(
    "failure_order",
    [
        ("denied", "query", "cancelled"),
        ("query", "cancelled", "denied"),
        ("cancelled", "denied", "query"),
        ("denied", "cancelled", "query"),
    ],
)
def test_valid_export_still_works_after_failure_sequence(
    failure_order: tuple[str, ...],
) -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    failures = {
        "denied": (AccessDenied, "project-private", {"project-a"}, None),
        "query": (
            QueryFailed,
            "project-query-error",
            {"project-query-error"},
            None,
        ),
        "cancelled": (ClientCancelled, "project-a", {"project-a"}, 2),
    }
    for name in failure_order:
        error, project_id, allowed, cancel_after = failures[name]
        with pytest.raises(error):
            service.export(project_id, allowed, cancel_after=cancel_after)

    rows = service.export("project-a", {"project-a"})
    assert len(rows) == 3
    assert pool.available == 4
