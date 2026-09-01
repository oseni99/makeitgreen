"""Deterministic connection pool used by the exercise."""
from __future__ import annotations

from copy import deepcopy

from audit_export.errors import PoolExhausted, QueryFailed


AUDIT_ROWS = {
    "project-a": [
        {"id": 3, "action": "deployment.created"},
        {"id": 1, "action": "project.created"},
        {"id": 2, "action": "member.invited"},
    ],
    "project-private": [{"id": 4, "action": "secret.rotated"}],
}


class AuditConnection:
    def __init__(self, connection_id: int, events: list[tuple[int, str]]) -> None:
        self.connection_id = connection_id
        self.state = "idle"
        self._events = events

    def begin(self) -> None:
        if self.state != "idle":
            raise RuntimeError(f"connection {self.connection_id} is {self.state}")
        self.state = "active"
        self._events.append((self.connection_id, "begin"))

    def stream(self, project_id: str):
        self._events.append((self.connection_id, "query"))
        if project_id == "project-query-error":
            self.state = "failed"
            raise QueryFailed("audit statement failed")
        for row in sorted(AUDIT_ROWS.get(project_id, []), key=lambda item: item["id"]):
            yield deepcopy(row)

    def commit(self) -> None:
        if self.state != "active":
            raise RuntimeError("cannot commit a non-active transaction")
        self._events.append((self.connection_id, "commit"))
        self.state = "idle"

    def rollback(self) -> None:
        if self.state not in {"active", "failed"}:
            raise RuntimeError("cannot roll back an idle connection")
        self._events.append((self.connection_id, "rollback"))
        self.state = "idle"


class ConnectionPool:
    def __init__(self, size: int = 4) -> None:
        self.events: list[tuple[int, str]] = []
        self.connections = [AuditConnection(i, self.events) for i in range(size)]
        self._available = list(reversed(self.connections))
        self._checked_out: set[int] = set()

    def acquire(self) -> AuditConnection:
        if not self._available:
            raise PoolExhausted("no audit connections available")
        connection = self._available.pop()
        self._checked_out.add(connection.connection_id)
        self.events.append((connection.connection_id, "acquire"))
        return connection

    def release(self, connection: AuditConnection) -> None:
        if connection.connection_id not in self._checked_out:
            raise RuntimeError("connection was not checked out")
        self.events.append((connection.connection_id, "release"))
        self._checked_out.remove(connection.connection_id)
        self._available.append(connection)

    @property
    def available(self) -> int:
        return len(self._available)

    @property
    def checked_out(self) -> int:
        return len(self._checked_out)
