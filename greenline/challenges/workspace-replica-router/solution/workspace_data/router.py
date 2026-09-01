"""Session-aware workspace primary/replica router."""
from __future__ import annotations

from workspace_data.cluster import ReplicaCluster, ReplicaUnavailable


class WorkspaceRouter:
    def __init__(self, cluster: ReplicaCluster) -> None:
        self.cluster = cluster
        self._session_watermarks: dict[str, int] = {}

    def rename(self, session_id: str, workspace_id: str, name: str) -> int:
        position = self.cluster.rename(workspace_id, name)
        self._session_watermarks[session_id] = max(
            position, self._session_watermarks.get(session_id, 0)
        )
        return position

    def get(self, session_id: str, workspace_id: str) -> dict:
        source = self._source_for(session_id)
        return {"workspace": self.cluster.read(source, workspace_id), "source": source}

    def list(self, session_id: str) -> dict:
        source = self._source_for(session_id)
        return {"workspaces": self.cluster.list_workspaces(source), "source": source}

    def _source_for(self, session_id: str) -> str:
        required = self._session_watermarks.get(session_id, 0)
        if self.cluster.replica_available and self.cluster.applied_position >= required:
            return "replica"
        return "primary"
