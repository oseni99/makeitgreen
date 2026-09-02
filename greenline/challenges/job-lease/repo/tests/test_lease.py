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


def test_expired_owner_cannot_renew_before_takeover() -> None:
    clock = Clock()
    store = LeaseStore(clock, ttl=10)
    lease = store.acquire("worker-a")
    assert lease is not None
    clock.value = 111
    assert store.renew(lease) is None


def test_stale_owner_cannot_renew_or_release_new_generation() -> None:
    clock = Clock()
    store = LeaseStore(clock, ttl=10)
    old = store.acquire("worker-a")
    assert old is not None
    clock.value = 111
    current = store.acquire("worker-a")
    assert current is not None
    assert store.renew(old) is None
    assert store.release(old) is False
    assert store.renew(current) is not None
