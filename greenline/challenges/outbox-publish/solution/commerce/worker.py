"""Retry-safe polling for the transactional outbox."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from commerce.store import Store


class Publisher(Protocol):
    def publish(self, event_id: str, topic: str, payload: dict) -> None: ...


class OutboxWorker:
    def __init__(
        self,
        store: Store,
        publisher: Publisher,
        clock: Callable[[], str],
    ) -> None:
        self.store = store
        self.publisher = publisher
        self.clock = clock

    def run_once(self, limit: int = 100) -> int:
        delivered = 0
        for event in self.store.pending_events(limit=limit):
            # Mark only after publish returns. Exceptions deliberately leave the
            # row pending for a later worker invocation.
            self.publisher.publish(event.id, event.topic, event.payload)
            self.store.mark_published(event.id, self.clock())
            delivered += 1
        return delivered
