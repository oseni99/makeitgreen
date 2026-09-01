"""Thread-safe deterministic queue with explicit acknowledgement."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from invoice_delivery.models import DeliveryCommand


@dataclass(frozen=True)
class Claim:
    tag: int
    command: DeliveryCommand


class InMemoryQueue:
    def __init__(self) -> None:
        self._lock = Lock()
        self._pending: list[tuple[int, DeliveryCommand]] = []
        self._inflight: dict[int, DeliveryCommand] = {}
        self._next_tag = 1
        self._next_sequence = 1
        self.parked: list[DeliveryCommand] = []

    def publish(self, command: DeliveryCommand) -> None:
        with self._lock:
            self._pending.append((self._next_sequence, command))
            self._next_sequence += 1

    def claim_ready(self, now: float) -> Claim | None:
        with self._lock:
            ready = [item for item in self._pending if item[1].ready_at <= now]
            if not ready:
                return None
            sequence, command = min(ready, key=lambda item: (item[1].ready_at, item[0]))
            self._pending.remove((sequence, command))
            tag = self._next_tag
            self._next_tag += 1
            self._inflight[tag] = command
            return Claim(tag, command)

    def ack(self, claim: Claim) -> None:
        with self._lock:
            self._require_claim(claim)
            del self._inflight[claim.tag]

    def retry(self, claim: Claim, ready_at: float, error: str) -> None:
        with self._lock:
            self._require_claim(claim)
            del self._inflight[claim.tag]
            self._pending.append(
                (self._next_sequence, claim.command.retry_at(ready_at, error))
            )
            self._next_sequence += 1

    def park(self, claim: Claim, error: str) -> None:
        with self._lock:
            self._require_claim(claim)
            del self._inflight[claim.tag]
            command = claim.command
            self.parked.append(
                DeliveryCommand(
                    message_id=command.message_id,
                    invoice_id=command.invoice_id,
                    destination=command.destination,
                    attempt=command.attempt,
                    ready_at=command.ready_at,
                    errors=(*command.errors, error),
                )
            )

    def redeliver_inflight(self) -> None:
        with self._lock:
            for command in self._inflight.values():
                self._pending.append((self._next_sequence, command))
                self._next_sequence += 1
            self._inflight.clear()

    def next_ready_at(self) -> float | None:
        with self._lock:
            if not self._pending:
                return None
            return min(command.ready_at for _, command in self._pending)

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def inflight(self) -> int:
        with self._lock:
            return len(self._inflight)

    def _require_claim(self, claim: Claim) -> None:
        if self._inflight.get(claim.tag) != claim.command:
            raise RuntimeError("claim is no longer in flight")
