from __future__ import annotations

import pytest

from commerce.service import OrderService
from commerce.store import Store


def test_validation_rejects_invalid_orders() -> None:
    service = OrderService(Store())
    with pytest.raises(ValueError, match="positive"):
        service.create_order("o-1", "c-1", 0)
    with pytest.raises(ValueError, match="required"):
        service.create_order("", "c-1", 100)


def test_create_writes_expected_order_and_event_payload() -> None:
    store = Store()
    order = OrderService(store).create_order("o-1", "c-7", 1299)

    assert store.get_order("o-1") == order
    event = store.get_event("order.created:o-1")
    assert event is not None
    assert event.topic == "order.created"
    assert event.payload == {
        "order_id": "o-1",
        "customer_id": "c-7",
        "total_cents": 1299,
    }


def test_order_and_outbox_are_atomic() -> None:
    store = Store()

    def fail_between_writes() -> None:
        raise RuntimeError("simulated enqueue outage")

    service = OrderService(store, before_enqueue=fail_between_writes)
    with pytest.raises(RuntimeError, match="enqueue outage"):
        service.create_order("o-atomic", "c-1", 500)

    assert store.get_order("o-atomic") is None
    assert store.outbox_count() == 0


def test_repeated_create_is_idempotent() -> None:
    store = Store()
    service = OrderService(store)

    first = service.create_order("o-repeat", "c-1", 500)
    second = service.create_order("o-repeat", "c-1", 500)

    assert second == first
    assert store.list_orders() == [first]
    assert store.outbox_count() == 1


@pytest.mark.parametrize(
    ("order_id", "customer_id", "total_cents"),
    [
        ("o-first", "c-1", 1),
        ("o-middle", "c-2", 500),
        ("o-large", "c-3", 1_000_000),
    ],
)
def test_each_order_write_rolls_back_when_outbox_enqueue_fails(
    order_id: str,
    customer_id: str,
    total_cents: int,
) -> None:
    store = Store()

    def fail_between_writes() -> None:
        raise RuntimeError("simulated enqueue outage")

    with pytest.raises(RuntimeError, match="enqueue outage"):
        OrderService(store, before_enqueue=fail_between_writes).create_order(
            order_id, customer_id, total_cents
        )

    assert store.get_order(order_id) is None
    assert store.outbox_count() == 0


def test_retrying_existing_order_id_returns_original_without_new_event() -> None:
    store = Store()
    service = OrderService(store)
    original = service.create_order("o-1", "original-customer", 100)

    retried = service.create_order("o-1", "changed-customer", 999)

    assert retried == original
    assert store.list_orders() == [original]
    assert store.outbox_count() == 1
