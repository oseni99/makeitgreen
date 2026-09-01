"""Transactional stand-in for the customer delivery boundary."""
from __future__ import annotations

from threading import Lock

from invoice_delivery.models import DeliveryCommand


class TransientDeliveryError(RuntimeError):
    pass


class DeliverySink:
    def __init__(self, failures: dict[str, int] | None = None) -> None:
        self._lock = Lock()
        self._failures = dict(failures or {})
        self.deliveries: list[dict[str, str]] = []
        self.processed_message_ids: set[str] = set()

    def deliver(self, command: DeliveryCommand) -> None:
        """Unsafe delivery used by the broken worker."""
        with self._lock:
            self._deliver_locked(command)

    def deliver_once(self, command: DeliveryCommand) -> bool:
        """Atomically record the effect and message identity.

        Returns False when another worker already committed this message.
        """
        with self._lock:
            if command.message_id in self.processed_message_ids:
                return False
            self._deliver_locked(command)
            self.processed_message_ids.add(command.message_id)
            return True

    def _deliver_locked(self, command: DeliveryCommand) -> None:
        remaining = self._failures.get(command.invoice_id, 0)
        if remaining > 0:
            self._failures[command.invoice_id] = remaining - 1
            raise TransientDeliveryError(f"destination unavailable for {command.invoice_id}")
        self.deliveries.append(
            {
                "message_id": command.message_id,
                "invoice_id": command.invoice_id,
                "destination": command.destination,
            }
        )
