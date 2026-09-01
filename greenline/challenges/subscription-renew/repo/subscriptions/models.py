"""Domain records for the renewal service."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass
class Subscription:
    id: str
    customer_id: str
    unit_price_cents: int
    seats: int
    discount_percent: int
    credit_cents: int
    next_billing_at: int
    status: str = "active"

    def copy(self) -> "Subscription":
        return replace(self)


@dataclass(frozen=True)
class RenewalReceipt:
    renewal_key: str
    subscription_id: str
    amount_cents: int
    next_billing_at: int


@dataclass(frozen=True)
class RenewalResult:
    renewed: bool
    receipt: RenewalReceipt | None
