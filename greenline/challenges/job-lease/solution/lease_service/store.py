from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Lease:
    owner: str
    generation: int
    expires_at: float


class LeaseStore:
    def __init__(self, now: Callable[[], float], ttl: float = 10.0) -> None:
        self._now = now
        self._ttl = ttl
        self._lease: Lease | None = None
        self._generation = 0

    def acquire(self, owner: str) -> Lease | None:
        if self._lease is not None and self._lease.expires_at > self._now():
            return None
        self._generation += 1
        self._lease = Lease(owner, self._generation, self._now() + self._ttl)
        return self._lease

    def _matches(self, lease: Lease) -> bool:
        return self._lease is not None and self._lease == lease and self._now() < self._lease.expires_at

    def renew(self, lease: Lease) -> Lease | None:
        if not self._matches(lease):
            return None
        self._lease = Lease(lease.owner, lease.generation, self._now() + self._ttl)
        return self._lease

    def release(self, lease: Lease) -> bool:
        if not self._matches(lease):
            return False
        self._lease = None
        return True
