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


@pytest.mark.parametrize(
    ("session", "workspace", "name"),
    [
        ("writer-a", "workspace-a", "Alpha New"),
        ("writer-a", "workspace-b", "Beta New"),
        ("writer-b", "workspace-a", "Alpha Other"),
        ("writer-b", "workspace-b", "Beta Other"),
    ],
)
def test_each_writer_session_reads_its_own_unreplicated_change(
    session: str,
    workspace: str,
    name: str,
) -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    router.rename(session, workspace, name)

    result = router.get(session, workspace)

    assert result["source"] == "primary"
    assert result["workspace"]["name"] == name


@pytest.mark.parametrize("write_count", [1, 2, 3])
def test_list_stays_on_primary_until_session_watermark_is_replicated(
    write_count: int,
) -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    last_position = 0
    for number in range(write_count):
        workspace = "workspace-a" if number % 2 == 0 else "workspace-b"
        last_position = router.rename("writer", workspace, f"Name {number}")

    assert router.list("writer")["source"] == "primary"
    cluster.advance_replica(last_position)
    assert router.list("writer")["source"] == "replica"


@pytest.mark.parametrize("session", ["reader-a", "reader-b"])
def test_each_reader_falls_back_to_primary_when_replica_is_unavailable(
    session: str,
) -> None:
    cluster = ReplicaCluster()
    router = WorkspaceRouter(cluster)
    cluster.replica_available = False

    result = router.get(session, "workspace-a")

    assert result["source"] == "primary"
    assert result["workspace"]["name"] == "Alpha"
