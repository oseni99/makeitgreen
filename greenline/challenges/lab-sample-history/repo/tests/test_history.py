import pytest

from history import HistoryDatabase


def test_simple_history_collapses_consecutive_duplicates() -> None:
    db = HistoryDatabase()
    db.add("t1", "s1", "a1", "e1", 1, 1, 1, "received")
    db.add("t1", "s1", "a1", "e2", 1, 2, 2, "received")
    db.add("t1", "s1", "a1", "e3", 1, 3, 3, "processed")

    assert db.report(3) == [
        ("t1", "s1", "a1", "received", None, 1),
        ("t1", "s1", "a1", "processed", "received", 2),
    ]


def test_same_ids_in_different_tenants_never_share_revision_or_history() -> None:
    db = HistoryDatabase()
    db.add("t1", "shared", "a1", "e1", 1, 1, 1, "received")
    db.add("t2", "shared", "a1", "e1", 2, 1, 1, "quarantined")

    assert db.report(1) == [
        ("t1", "shared", "a1", "received", None, 1),
        ("t2", "shared", "a1", "quarantined", None, 1),
    ]


def test_aliquots_have_independent_transition_windows() -> None:
    db = HistoryDatabase()
    db.add("t1", "s1", "a1", "e1", 1, 1, 1, "received")
    db.add("t1", "s1", "a2", "e2", 1, 2, 2, "processed")
    db.add("t1", "s1", "a1", "e3", 1, 3, 3, "processed")

    assert db.report(3) == [
        ("t1", "s1", "a1", "received", None, 1),
        ("t1", "s1", "a1", "processed", "received", 2),
        ("t1", "s1", "a2", "processed", None, 1),
    ]


def test_latest_revision_visible_at_cutoff_replaces_payload_not_identity() -> None:
    db = HistoryDatabase()
    db.add("t1", "s1", "a1", "e1", 1, 1, 1, "received")
    db.add("t1", "s1", "a1", "e1", 2, 1, 5, "quarantined")

    assert db.report(4) == [("t1", "s1", "a1", "received", None, 1)]
    assert db.report(5) == [("t1", "s1", "a1", "quarantined", None, 1)]


def test_simultaneous_observations_use_event_id_as_stable_tie_breaker() -> None:
    db = HistoryDatabase()
    db.add("t1", "s1", "a1", "e2", 1, 10, 1, "processed")
    db.add("t1", "s1", "a1", "e1", 1, 10, 1, "received")

    assert db.report(1) == [
        ("t1", "s1", "a1", "received", None, 1),
        ("t1", "s1", "a1", "processed", "received", 2),
    ]


@pytest.mark.parametrize("other_revision", [2, 3, 10])
def test_revision_selection_is_scoped_by_tenant(other_revision: int) -> None:
    db = HistoryDatabase()
    db.add("tenant-a", "shared", "a1", "event", 1, 1, 1, "received")
    db.add(
        "tenant-b", "shared", "a1", "event", other_revision, 1, 1, "processed"
    )

    assert db.report(1) == [
        ("tenant-a", "shared", "a1", "received", None, 1),
        ("tenant-b", "shared", "a1", "processed", None, 1),
    ]


@pytest.mark.parametrize("other_revision", [2, 3, 10])
def test_revision_selection_is_scoped_by_aliquot(other_revision: int) -> None:
    db = HistoryDatabase()
    db.add("tenant", "sample", "a1", "event", 1, 1, 1, "received")
    db.add(
        "tenant", "sample", "a2", "event", other_revision, 1, 1, "processed"
    )

    assert db.report(1) == [
        ("tenant", "sample", "a1", "received", None, 1),
        ("tenant", "sample", "a2", "processed", None, 1),
    ]


@pytest.mark.parametrize("states", [("received", "processed"), ("queued", "failed")])
def test_aliquot_transition_numbering_starts_independently(
    states: tuple[str, str],
) -> None:
    db = HistoryDatabase()
    db.add("tenant", "sample", "a1", "e1", 1, 1, 1, states[0])
    db.add("tenant", "sample", "a2", "e2", 1, 2, 1, states[1])

    assert db.report(1) == [
        ("tenant", "sample", "a1", states[0], None, 1),
        ("tenant", "sample", "a2", states[1], None, 1),
    ]


@pytest.mark.parametrize("cutoff", [1, 5])
def test_invisible_revision_does_not_hide_visible_event(cutoff: int) -> None:
    db = HistoryDatabase()
    db.add("tenant-a", "shared", "a1", "event", 1, 1, cutoff, "received")
    db.add("tenant-b", "shared", "a1", "event", 9, 1, cutoff + 1, "failed")

    assert db.report(cutoff) == [
        ("tenant-a", "shared", "a1", "received", None, 1)
    ]
