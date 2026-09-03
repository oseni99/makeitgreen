from dataclasses import dataclass
from threading import Lock
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
        self._lock = Lock()

    def acquire(self, owner: str) -> Lease | None:
        with self._lock:
            now = self._now()
            if self._lease is not None and self._lease.expires_at > now:
                return None
            self._generation += 1
            self._lease = Lease(owner, self._generation, now + self._ttl)
            return self._lease

    def _matches(self, lease: Lease, now: float) -> bool:
        return (
            self._lease is not None
            and self._lease == lease
            and now < self._lease.expires_at
        )

    def renew(self, lease: Lease) -> Lease | None:
        with self._lock:
            now = self._now()
            if not self._matches(lease, now):
                return None
            self._lease = Lease(lease.owner, lease.generation, now + self._ttl)
            return self._lease

    def release(self, lease: Lease) -> bool:
        with self._lock:
            now = self._now()
            if not self._matches(lease, now):
                return False
            self._lease = None
            return True
