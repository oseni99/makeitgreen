from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from scheduler import DigestScheduler, JobStore, LeaseLost, RecordingSink


def test_only_one_worker_claims_a_due_job() -> None:
    gate = Barrier(2)
    store = JobStore(before_claim=lambda: gate.wait(timeout=1))
    store.add("daily-1", due_at=10)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda worker: store.claim("daily-1", worker, now=10, lease_seconds=5), ["a", "b"]))

    assert sum(claim is not None for claim in claims) == 1


def test_not_yet_due_job_cannot_be_claimed() -> None:
    store = JobStore()
    store.add("daily-1", due_at=11)
    assert store.claim("daily-1", "a", now=10, lease_seconds=5) is None


def test_expired_claim_gets_a_new_fencing_generation() -> None:
    store = JobStore()
    store.add("daily-1", due_at=0)
    first = store.claim("daily-1", "worker", now=0, lease_seconds=5)
    second = store.claim("daily-1", "worker", now=5, lease_seconds=5)

    assert (first, second) == (1, 2)


def test_stale_generation_cannot_deliver_after_reassignment() -> None:
    store = JobStore()
    sink = RecordingSink()
    scheduler = DigestScheduler(store, sink)
    store.add("daily-1", due_at=0)
    first = store.claim("daily-1", "worker", now=0, lease_seconds=5)
    second = store.claim("daily-1", "worker", now=5, lease_seconds=5)

    with pytest.raises(LeaseLost):
        scheduler.execute("daily-1", "worker", first, now=5)
    scheduler.execute("daily-1", "worker", second, now=5)

    assert sink.deliveries == ["daily-1"]


def test_expired_owner_cannot_complete_without_a_reclaim() -> None:
    store = JobStore()
    sink = RecordingSink()
    scheduler = DigestScheduler(store, sink)
    store.add("daily-1", due_at=0)
    generation = store.claim("daily-1", "a", now=0, lease_seconds=5)

    with pytest.raises(LeaseLost):
        scheduler.execute("daily-1", "a", generation, now=5)
    assert sink.deliveries == []


def test_completed_job_is_not_claimed_or_delivered_twice() -> None:
    store = JobStore()
    sink = RecordingSink()
    scheduler = DigestScheduler(store, sink)
    store.add("daily-1", due_at=0)
    generation = store.claim("daily-1", "a", now=0, lease_seconds=5)
    scheduler.execute("daily-1", "a", generation, now=1)

    assert store.claim("daily-1", "b", now=10, lease_seconds=5) is None
    with pytest.raises(LeaseLost):
        scheduler.execute("daily-1", "a", generation, now=1)
    assert sink.deliveries == ["daily-1"]


@pytest.mark.parametrize("worker_count", [3, 4, 8])
def test_exactly_one_of_many_workers_claims_the_same_due_job(
    worker_count: int,
) -> None:
    gate = Barrier(worker_count)
    store = JobStore(before_claim=lambda: gate.wait(timeout=1))
    store.add("daily-1", due_at=0)

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        claims = list(
            pool.map(
                lambda worker: store.claim(
                    "daily-1", worker, now=0, lease_seconds=5
                ),
                [f"worker-{number}" for number in range(worker_count)],
            )
        )

    assert sum(claim is not None for claim in claims) == 1


@pytest.mark.parametrize("generation", [0, 2, 99])
def test_unissued_generation_cannot_execute_for_the_current_owner(
    generation: int,
) -> None:
    store = JobStore()
    sink = RecordingSink()
    scheduler = DigestScheduler(store, sink)
    store.add("daily-1", due_at=0)
    assert store.claim("daily-1", "worker", now=0, lease_seconds=5) == 1

    with pytest.raises(LeaseLost):
        scheduler.execute("daily-1", "worker", generation, now=1)
    assert sink.deliveries == []


@pytest.mark.parametrize("now", [5, 6, 100])
def test_owner_cannot_execute_at_or_after_lease_expiry(now: int) -> None:
    store = JobStore()
    sink = RecordingSink()
    scheduler = DigestScheduler(store, sink)
    store.add("daily-1", due_at=0)
    generation = store.claim("daily-1", "worker", now=0, lease_seconds=5)

    with pytest.raises(LeaseLost):
        scheduler.execute("daily-1", "worker", generation, now=now)
    assert sink.deliveries == []
