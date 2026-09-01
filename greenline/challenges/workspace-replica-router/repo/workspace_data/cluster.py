"""Deterministic asynchronous replica model."""
from __future__ import annotations

from copy import deepcopy


class WorkspaceNotFound(LookupError):
    pass


class ReplicaUnavailable(RuntimeError):
    pass


class ReplicaCluster:
    def __init__(self) -> None:
        initial = {
            "workspace-a": {"id": "workspace-a", "name": "Alpha"},
            "workspace-b": {"id": "workspace-b", "name": "Beta"},
        }
        self.primary = deepcopy(initial)
        self.replica = deepcopy(initial)
        self.commit_position = 0
        self.applied_position = 0
        self.replica_available = True
        self._snapshots: dict[int, dict[str, dict]] = {0: deepcopy(initial)}

    def rename(self, workspace_id: str, name: str) -> int:
        if workspace_id not in self.primary:
            raise WorkspaceNotFound(workspace_id)
        if not name.strip():
            raise ValueError("name is required")
        self.commit_position += 1
        self.primary[workspace_id]["name"] = name
        self._snapshots[self.commit_position] = deepcopy(self.primary)
        return self.commit_position

    def advance_replica(self, position: int) -> None:
        if position < self.applied_position or position > self.commit_position:
            raise ValueError("invalid replica position")
        self.replica = deepcopy(self._snapshots[position])
        self.applied_position = position

    def read(self, source: str, workspace_id: str) -> dict:
        store = self._store(source)
        try:
            return deepcopy(store[workspace_id])
        except KeyError as exc:
            raise WorkspaceNotFound(workspace_id) from exc

    def list_workspaces(self, source: str) -> list[dict]:
        store = self._store(source)
        return [deepcopy(store[key]) for key in sorted(store)]

    def _store(self, source: str) -> dict[str, dict]:
        if source == "primary":
            return self.primary
        if source == "replica":
            if not self.replica_available:
                raise ReplicaUnavailable("replica is unavailable")
            return self.replica
        raise ValueError(f"unknown source: {source}")
