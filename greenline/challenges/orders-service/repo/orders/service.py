"""Order creation, pricing, checkout, and cancellation."""
from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass

from orders.inventory import InsufficientStock, Inventory

_order_ids = itertools.count(1)

DISCOUNT_TIERS = [
    (10_000, 0.10),
    (5_000, 0.05),
]


@dataclass
class Order:
    id: int
    sku: str
    qty: int
    unit_price_cents: int
    discount_cents: int = 0
    status: str = "created"

    @property
    def subtotal_cents(self) -> int:
        return self.qty * self.unit_price_cents

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents - self.discount_cents


class OrderService:
    def __init__(
        self,
        inventory: Inventory,
        before_checkout: Callable[[Order], None] | None = None,
    ) -> None:
        self.inventory = inventory
        self.orders: dict[int, Order] = {}
        self._before_checkout = before_checkout or (lambda _order: None)

    def create_order(self, sku: str, qty: int, unit_price_cents: int) -> Order:
        if qty <= 0:
            raise ValueError("qty must be positive")
        order = Order(
            id=next(_order_ids),
            sku=sku,
            qty=qty,
            unit_price_cents=unit_price_cents,
        )
        self.orders[order.id] = order
        return order

    def apply_discount(self, order: Order) -> Order:
        for threshold, rate in DISCOUNT_TIERS:
            if order.subtotal_cents >= threshold:
                order.discount_cents = int(order.subtotal_cents * rate)
                break
        return order

    def checkout(self, order: Order) -> bool:
        self._before_checkout(order)
        order.status = "processing"
        try:
            self.inventory.reserve(order.sku, order.qty)
        except InsufficientStock:
            order.status = "rejected"
            return False
        order.status = "completed"
        return True

    def cancel(self, order: Order) -> bool:
        order.status = "cancelled"
        return True
