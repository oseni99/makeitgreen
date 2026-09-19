from __future__ import annotations

import pytest

from commerce.service import OrderService
from commerce.store import Store
from commerce.worker import OutboxWorker


class FakePublisher:
    def __init__(self) -> None:
        self.attempts: list[str] = []
        self.delivered: dict[str, tuple[str, dict]] = {}
        self.failures_remaining = 0

    def fail_next(self) -> None:
        self.failures_remaining += 1

    def publish(self, event_id: str, topic: str, payload: dict) -> None:
        self.attempts.append(event_id)
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise ConnectionError("broker unavailable")
        # Consumers deduplicate the stable event ID.
        self.delivered.setdefault(event_id, (topic, payload))


def _worker(store: Store, publisher: FakePublisher) -> OutboxWorker:
    return OutboxWorker(
        store,
        publisher,
        clock=lambda: "2026-08-30T12:00:00+00:00",
    )


def test_empty_outbox_is_a_noop() -> None:
    publisher = FakePublisher()
    assert _worker(Store(), publisher).run_once() == 0
    assert publisher.attempts == []


def test_success_marks_published_and_prevents_duplicate_poll_delivery() -> None:
    store = Store()
    OrderService(store).create_order("o-1", "c-1", 100)
    publisher = FakePublisher()
    worker = _worker(store, publisher)

    assert worker.run_once() == 1
    assert worker.run_once() == 0
    assert publisher.attempts == ["order.created:o-1"]
    assert store.get_event("order.created:o-1").published_at == (
        "2026-08-30T12:00:00+00:00"
    )


def test_failed_publish_stays_pending_then_retries() -> None:
    store = Store()
    OrderService(store).create_order("o-retry", "c-1", 100)
    publisher = FakePublisher()
    publisher.fail_next()
    worker = _worker(store, publisher)

    with pytest.raises(ConnectionError, match="broker unavailable"):
        worker.run_once()
    assert store.get_event("order.created:o-retry").published_at is None

    assert worker.run_once() == 1
    assert publisher.attempts == [
        "order.created:o-retry",
        "order.created:o-retry",
    ]
    assert list(publisher.delivered) == ["order.created:o-retry"]
    assert store.get_event("order.created:o-retry").published_at is not None


def test_worker_publishes_pending_rows_in_fifo_order() -> None:
    store = Store()
    service = OrderService(store)
    service.create_order("o-1", "c-1", 100)
    service.create_order("o-2", "c-2", 200)
    publisher = FakePublisher()

    assert _worker(store, publisher).run_once() == 2
    assert publisher.attempts == ["order.created:o-1", "order.created:o-2"]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_success_marks_every_row_selected_by_the_poll_limit(limit: int) -> None:
    store = Store()
    service = OrderService(store)
    for number in range(1, 4):
        service.create_order(f"o-{number}", f"c-{number}", number * 100)
    publisher = FakePublisher()
    worker = _worker(store, publisher)

    assert worker.run_once(limit=limit) == limit
    for number in range(1, limit + 1):
        assert store.get_event(f"order.created:o-{number}").published_at is not None
