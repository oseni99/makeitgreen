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


def test_repeated_access_denials_do_not_exhaust_pool() -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    for _ in range(6):
        with pytest.raises(AccessDenied):
            service.export("project-private", {"project-a"})

    assert pool.available == 4
    assert pool.checked_out == 0
    assert all(connection.state == "idle" for connection in pool.connections)


def test_query_failure_rolls_back_before_release() -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    with pytest.raises(QueryFailed, match="statement failed"):
        service.export("project-query-error", {"project-query-error"})

    assert pool.events[-2:] == [(0, "rollback"), (0, "release")]
    assert pool.available == 4
    assert pool.connections[0].state == "idle"


def test_client_cancellation_rolls_back_and_returns_connection() -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    with pytest.raises(ClientCancelled, match="after 1 rows"):
        service.export("project-a", {"project-a"}, cancel_after=1)

    assert pool.events[-2:] == [(0, "rollback"), (0, "release")]
    assert pool.available == 4
    assert pool.connections[0].state == "idle"


def test_valid_export_still_works_after_failure_sequence() -> None:
    pool = ConnectionPool()
    service = AuditExportService(pool)

    with pytest.raises(AccessDenied):
        service.export("project-private", {"project-a"})
    with pytest.raises(QueryFailed):
        service.export("project-query-error", {"project-query-error"})
    with pytest.raises(ClientCancelled):
        service.export("project-a", {"project-a"}, cancel_after=2)

    rows = service.export("project-a", {"project-a"})
    assert len(rows) == 3
    assert pool.available == 4
