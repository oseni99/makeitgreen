"""Order rows feeding the customer spend report."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    order_id: int
    customer_id: str
    sku: str
    qty: int
    unit_price_cents: int

    @property
    def total_cents(self) -> int:
        return self.qty * self.unit_price_cents
