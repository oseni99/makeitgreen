from __future__ import annotations

from collections import deque
from collections.abc import Callable
from threading import Barrier


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
        # BUG: all tenants share one window, and mutations are not synchronized.
        self._events: deque[float] = deque()

    def allow(self, tenant: str) -> bool:
        if not tenant:
            raise ValueError("tenant is required")
        now = self.clock()
        cutoff = now - self.window_seconds
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()
        if len(self._events) >= self.limit:
            return False
        # The probe exposes the check-then-record race deterministically.
        if self.decision_gate is not None:
            self.decision_gate.wait(timeout=2)
        self._events.append(now)
        return True
