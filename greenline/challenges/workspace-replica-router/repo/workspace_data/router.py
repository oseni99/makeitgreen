"""Workspace router that currently sends every read to the replica."""
from __future__ import annotations

from workspace_data.cluster import ReplicaCluster


class WorkspaceRouter:
    def __init__(self, cluster: ReplicaCluster) -> None:
        self.cluster = cluster

    def rename(self, session_id: str, workspace_id: str, name: str) -> int:
        # BUG: the returned commit dependency is discarded.
        return self.cluster.rename(workspace_id, name)

    def get(self, session_id: str, workspace_id: str) -> dict:
        # BUG: asynchronous replicas cannot guarantee a session sees its write.
        return {"workspace": self.cluster.read("replica", workspace_id), "source": "replica"}

    def list(self, session_id: str) -> dict:
        return {"workspaces": self.cluster.list_workspaces("replica"), "source": "replica"}
