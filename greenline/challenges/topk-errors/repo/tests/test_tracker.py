from __future__ import annotations

import pytest

from topk import ErrorTracker


def test_exact_counts_and_deterministic_ties_below_capacity() -> None:
    tracker = ErrorTracker(k=2, capacity=8)
    for service in ["api", "worker", "api", "billing", "worker"]:
        tracker.ingest(service, "ERROR")

    assert tracker.topk() == [("api", 2), ("worker", 2)]


def test_non_errors_do_not_enter_the_tracker() -> None:
    tracker = ErrorTracker(k=1, capacity=2)
    tracker.ingest("chatty", "WARN")
    tracker.ingest("healthy", "INFO")
    tracker.ingest("broken", "ERROR")

    assert tracker.topk() == [("broken", 1)]
    assert tracker.tracked_services == 1


def test_rejects_impossible_configuration() -> None:
    with pytest.raises(ValueError):
        ErrorTracker(k=0, capacity=4)
    with pytest.raises(ValueError):
        ErrorTracker(k=3, capacity=2)


def test_state_never_exceeds_capacity_under_cardinality_spike() -> None:
    tracker = ErrorTracker(k=3, capacity=12)
    for i in range(2_000):
        tracker.ingest(f"ephemeral-{i}", "ERROR")

    assert tracker.tracked_services <= 12
    # This challenge is specifically about retained counter state. Verify the
    # storage itself so reporting a fake size cannot satisfy the invariant.
    assert len(tracker._counts) <= 12


def test_clearly_dominant_services_survive_noisy_stream() -> None:
    tracker = ErrorTracker(k=2, capacity=16)
    for i in range(600):
        tracker.ingest("checkout", "ERROR")
        if i % 2 == 0:
            tracker.ingest("payments", "ERROR")
        tracker.ingest(f"noise-{i}", "ERROR")

    names = [service for service, _estimate in tracker.topk()]
    assert names == ["checkout", "payments"]
    assert tracker.tracked_services <= 16
    assert len(tracker._counts) <= 16


@pytest.mark.parametrize(
    ("k", "capacity", "cardinality"),
    [
        (1, 1, 2),
        (1, 2, 3),
        (2, 2, 4),
        (2, 3, 10),
        (3, 4, 25),
        (3, 8, 100),
        (4, 8, 500),
        (5, 10, 1_000),
        (5, 16, 2_000),
        (10, 32, 5_000),
    ],
)
def test_counter_storage_is_bounded_for_each_capacity_and_cardinality(
    k: int,
    capacity: int,
    cardinality: int,
) -> None:
    tracker = ErrorTracker(k=k, capacity=capacity)
    for number in range(cardinality):
        tracker.ingest(f"service-{number}", "ERROR")

    assert tracker.tracked_services <= capacity
    assert len(tracker._counts) <= capacity
    assert len(tracker.topk()) <= k
