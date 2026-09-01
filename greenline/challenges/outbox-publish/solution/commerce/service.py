"""Atomic and idempotent order creation with a transactional outbox."""
from __future__ import annotations

from collections.abc import Callable

from commerce.models import Order, OutboxEvent
from commerce.store import Store


class OrderService:
    def __init__(
        self,
        store: Store,
        before_enqueue: Callable[[], None] | None = None,
    ) -> None:
        self.store = store
        self.before_enqueue = before_enqueue

    def create_order(self, order_id: str, customer_id: str, total_cents: int) -> Order:
        if not order_id or not customer_id:
            raise ValueError("order_id and customer_id are required")
        if total_cents <= 0:
            raise ValueError("total_cents must be positive")

        with self.store.transaction():
            existing = self.store.get_order(order_id)
            if existing is not None:
                return existing

            order = Order(order_id, customer_id, total_cents)
            self.store.insert_order(order)
            if self.before_enqueue is not None:
                self.before_enqueue()
            self.store.enqueue(
                OutboxEvent(
                    id=f"order.created:{order_id}",
                    topic="order.created",
                    payload={
                        "order_id": order_id,
                        "customer_id": customer_id,
                        "total_cents": total_cents,
                    },
                    published_at=None,
                ),
                order_id=order_id,
            )
            return order
