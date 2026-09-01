"""Order creation and checkout."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from orders.inventory import InsufficientStock, Inventory

_order_ids = itertools.count(1)

DISCOUNT_TIERS = [
    (10_000, 0.10),  # 10% off orders of $100+
    (5_000, 0.05),   # 5% off orders of $50+
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
    def __init__(self, inventory: Inventory) -> None:
        self.inventory = inventory
        self.orders: dict[int, Order] = {}

    def create_order(self, sku: str, qty: int, unit_price_cents: int) -> Order:
        if qty <= 0:
            raise ValueError("qty must be positive")
        order = Order(id=next(_order_ids), sku=sku, qty=qty,
                      unit_price_cents=unit_price_cents)
        self.orders[order.id] = order
        return order

    def apply_discount(self, order: Order) -> Order:
        for threshold, rate in DISCOUNT_TIERS:
            if order.subtotal_cents >= threshold:
                order.discount_cents = int(order.subtotal_cents * rate)
                break
        return order

    def checkout(self, order: Order) -> bool:
        """Reserve inventory and complete the order.

        Returns True if checkout succeeded, False if stock ran out.
        Called concurrently from checkout worker threads.
        """
        try:
            self.inventory.reserve(order.sku, order.qty)
        except InsufficientStock:
            order.status = "rejected"
            return False
        order.status = "completed"
        return True
