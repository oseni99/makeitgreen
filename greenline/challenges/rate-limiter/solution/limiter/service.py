from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from threading import Barrier, Lock


class RateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float],
        decision_gate: Barrier | None = None,
    ) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self.decision_gate = decision_gate
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, tenant: str) -> bool:
        if not tenant:
            raise ValueError("tenant is required")
        # Synchronize the test callers before, never inside, the critical section.
        if self.decision_gate is not None:
            self.decision_gate.wait(timeout=2)
        with self._lock:
            # Sampling under the lock keeps the deque ordered by admission time.
            now = self.clock()
            events = self._events[tenant]
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True
