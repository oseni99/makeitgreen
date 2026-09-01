from __future__ import annotations


class ErrorTracker:
    def __init__(self, *, k: int, capacity: int) -> None:
        if k < 1 or capacity < k:
            raise ValueError("capacity must be at least k >= 1")
        self.k = k
        self.capacity = capacity
        # BUG: this grows once for every distinct service ever observed.
        self._counts: dict[str, int] = {}

    @property
    def tracked_services(self) -> int:
        return len(self._counts)

    def ingest(self, service: str, level: str) -> None:
        if level != "ERROR":
            return
        self._counts[service] = self._counts.get(service, 0) + 1

    def topk(self) -> list[tuple[str, int]]:
        return sorted(self._counts.items(), key=lambda item: (-item[1], item[0]))[: self.k]
