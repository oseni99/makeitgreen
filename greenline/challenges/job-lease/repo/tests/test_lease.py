from threading import Barrier, Event, Lock, Thread

import pytest

from lease_service.store import LeaseStore


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def test_valid_owner_can_renew() -> None:
    clock = Clock()
    store = LeaseStore(clock, ttl=10)
    lease = store.acquire("worker-a")
    assert lease is not None
    clock.value += 5
    renewed = store.renew(lease)
    assert renewed is not None
    assert renewed.expires_at == 115


def test_expired_lease_can_be_taken_by_new_owner() -> None:
    clock = Clock()
    store = LeaseStore(clock, ttl=10)
    old = store.acquire("worker-a")
    assert old is not None
    clock.value = 111
    current = store.acquire("worker-a")
    assert current is not None
    assert current.generation > old.generation


@pytest.mark.parametrize("elapsed", [10, 11, 100])
def test_expired_owner_cannot_renew_before_takeover(elapsed: float) -> None:
    clock = Clock()
    store = LeaseStore(clock, ttl=10)
    lease = store.acquire("worker-a")
    assert lease is not None
    clock.value += elapsed
    assert store.renew(lease) is None


@pytest.mark.parametrize(
    ("ttl", "elapsed"),
    [(1, 2), (5, 6), (10, 11), (30, 31)],
)
def test_stale_owner_cannot_renew_or_release_new_generation(
    ttl: float, elapsed: float
) -> None:
    clock = Clock()
    store = LeaseStore(clock, ttl=ttl)
    old = store.acquire("worker-a")
    assert old is not None
    clock.value += elapsed
    current = store.acquire("worker-a")
    assert current is not None
    assert store.renew(old) is None
    assert store.release(old) is False
    assert store.renew(current) is not None


@pytest.mark.parametrize("ttl", [1, 2, 5, 10, 30, 60])
def test_only_one_worker_acquires_an_available_lease(ttl: float) -> None:
    ready = Barrier(2)
    both_started = Event()
    started_lock = Lock()
    started = 0

    def coordinated_now() -> float:
        both_started.wait()
        return 100.0

    store = LeaseStore(coordinated_now, ttl=ttl)
    acquired = []

    def acquire(owner: str) -> None:
        nonlocal started
        ready.wait()
        with started_lock:
            started += 1
            if started == 2:
                both_started.set()
        acquired.append(store.acquire(owner))

    workers = [
        Thread(target=acquire, args=(owner,))
        for owner in ("worker-a", "worker-b")
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    leases = [lease for lease in acquired if lease is not None]
    assert len(leases) == 1
    assert leases[0].generation == 1
