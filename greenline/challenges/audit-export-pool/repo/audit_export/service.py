"""Audit export orchestration."""
from __future__ import annotations

from audit_export.errors import AccessDenied, ClientCancelled
from audit_export.pool import ConnectionPool


class AuditExportService:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def export(
        self,
        project_id: str,
        allowed_projects: set[str],
        *,
        cancel_after: int | None = None,
    ) -> list[dict]:
        connection = self.pool.acquire()
        connection.begin()

        # BUG: every exception below jumps over transaction and pool cleanup.
        if project_id not in allowed_projects:
            raise AccessDenied(project_id)

        rows: list[dict] = []
        for row in connection.stream(project_id):
            rows.append(row)
            if cancel_after is not None and len(rows) >= cancel_after:
                raise ClientCancelled(f"cancelled after {len(rows)} rows")

        connection.commit()
        self.pool.release(connection)
        return rows
