from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Snapshot:
    version: int
    values: dict[str, bool]


class MemoryFlagSource:
    def __init__(self, snapshots: dict[str, Snapshot]):
        self.snapshots = snapshots
        self.calls: list[str] = []
        self.failure: Exception | None = None

    def fetch(self, environment: str) -> Snapshot:
        self.calls.append(environment)
        if self.failure is not None:
            raise self.failure
        snapshot = self.snapshots[environment]
        return Snapshot(snapshot.version, dict(snapshot.values))
