"""Session read-after-write contract for replica routing."""

import pytest

from workspace_data.cluster import ReplicaCluster, WorkspaceNotFound
from workspace_data.router import WorkspaceRouter


def test_sessions_without_writes_use_replica() -> None:
    router = WorkspaceRouter(ReplicaCluster())
    result = router.get("reader", "workspace-a")
    assert result == {
        "workspace": {"id": "workspace-a", "name": "Alpha"},
        "source": "replica",
    }


def test_writer_reads_own_change_while_unrelated_session_stays_on_replica() -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    router.rename("writer", "workspace-a", "Alpha Next")

    writer = router.get("writer", "workspace-a")
    reader = router.get("reader", "workspace-a")
    assert writer == {
        "workspace": {"id": "workspace-a", "name": "Alpha Next"},
        "source": "primary",
    }
    assert reader == {
        "workspace": {"id": "workspace-a", "name": "Alpha"},
        "source": "replica",
    }


def test_replica_is_used_again_at_exact_required_position() -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    position = router.rename("writer", "workspace-a", "Alpha Next")
    cluster.advance_replica(position)

    result = router.get("writer", "workspace-a")
    assert result["source"] == "replica"
    assert result["workspace"]["name"] == "Alpha Next"


def test_session_watermark_is_monotonic_across_several_writes() -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    first = router.rename("writer", "workspace-a", "Alpha Two")
    second = router.rename("writer", "workspace-b", "Beta Two")
    cluster.advance_replica(first)

    result = router.list("writer")
    assert result["source"] == "primary"
    assert [item["name"] for item in result["workspaces"]] == ["Alpha Two", "Beta Two"]

    cluster.advance_replica(second)
    assert router.list("writer")["source"] == "replica"


def test_failed_write_does_not_pin_session_to_primary() -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    with pytest.raises(WorkspaceNotFound):
        router.rename("writer", "missing", "Nope")
    assert router.get("writer", "workspace-a")["source"] == "replica"


def test_unavailable_replica_falls_back_without_changing_dependency() -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    cluster.replica_available = False
    result = router.get("reader", "workspace-a")
    assert result["source"] == "primary"

    cluster.replica_available = True
    assert router.get("reader", "workspace-a")["source"] == "replica"
