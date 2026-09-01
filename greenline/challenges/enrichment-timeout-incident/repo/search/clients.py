from __future__ import annotations


class DownstreamTimeout(RuntimeError):
    pass


class FakeClock:
    def __init__(self) -> None:
        self.elapsed_ms = 0

    def advance(self, milliseconds: int) -> None:
        self.elapsed_ms += milliseconds


class EnrichmentClient:
    def __init__(self, clock: FakeClock, *, latency_ms: int = 100) -> None:
        self.clock = clock
        self.latency_ms = latency_ms
        self.fail_with: Exception | None = None
        self.calls: list[int | None] = []

    def enrich(self, query: str, timeout_ms: int | None) -> list[str]:
        self.calls.append(timeout_ms)
        if self.fail_with is not None:
            raise self.fail_with
        if timeout_ms is not None and self.latency_ms > timeout_ms:
            self.clock.advance(timeout_ms)
            raise DownstreamTimeout("enrichment deadline exceeded")
        self.clock.advance(self.latency_ms)
        return [f"label:{query}"]
