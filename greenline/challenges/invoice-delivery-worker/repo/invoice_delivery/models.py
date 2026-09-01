"""Commands and deterministic time for invoice delivery."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class DeliveryCommand:
    message_id: str
    invoice_id: str
    destination: str
    attempt: int = 1
    ready_at: float = 0.0
    errors: tuple[str, ...] = ()

    def retry_at(self, ready_at: float, error: str) -> "DeliveryCommand":
        return replace(
            self,
            attempt=self.attempt + 1,
            ready_at=ready_at,
            errors=(*self.errors, error),
        )


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("clock cannot move backward")
        self._now += seconds
