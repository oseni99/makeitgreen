from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from flag_source import Snapshot


class Source(Protocol):
    def fetch(self, environment: str) -> Snapshot: ...


@dataclass(frozen=True)
class CachedSnapshot:
    snapshot: Snapshot
    refreshed_at: float


class FlagClient:
    def __init__(self, source: Source, *, clock: Callable[[], float], ttl_seconds: float):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._source = source
        self._clock = clock
        self._ttl = ttl_seconds
        self._cache: dict[str, CachedSnapshot] = {}

    def enabled(self, environment: str, key: str, *, default: bool = False) -> bool:
        now = self._clock()
        cached = self._cache.get(environment)
        if cached is None or now - cached.refreshed_at >= self._ttl:
            try:
                snapshot = self._source.fetch(environment)
            except Exception:
                if cached is None:
                    raise
            else:
                cached = CachedSnapshot(snapshot, now)
                self._cache[environment] = cached
        assert cached is not None
        return cached.snapshot.values.get(key, default)
