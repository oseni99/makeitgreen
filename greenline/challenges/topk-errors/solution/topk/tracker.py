from __future__ import annotations


class ErrorTracker:
    """Space-Saving heavy hitters with a fixed number of counters."""

    def __init__(self, *, k: int, capacity: int) -> None:
        if k < 1 or capacity < k:
            raise ValueError("capacity must be at least k >= 1")
        self.k = k
        self.capacity = capacity
        self._counts: dict[str, int] = {}

    @property
    def tracked_services(self) -> int:
        return len(self._counts)

    def ingest(self, service: str, level: str) -> None:
        if level != "ERROR":
            return
        if service in self._counts:
            self._counts[service] += 1
            return
        if len(self._counts) < self.capacity:
            self._counts[service] = 1
            return

        victim, estimate = min(self._counts.items(), key=lambda item: (item[1], item[0]))
        del self._counts[victim]
        self._counts[service] = estimate + 1

    def topk(self) -> list[tuple[str, int]]:
        return sorted(self._counts.items(), key=lambda item: (-item[1], item[0]))[: self.k]
