"""Deterministic repository and payment test doubles."""
from __future__ import annotations

from .models import RenewalReceipt, Subscription


class PaymentDeclined(RuntimeError):
    pass


class SubscriptionRepository:
    def __init__(self, subscriptions: list[Subscription]) -> None:
        self._subscriptions = {item.id: item.copy() for item in subscriptions}
        self._receipts: dict[str, RenewalReceipt] = {}

    def get(self, subscription_id: str) -> Subscription:
        return self._subscriptions[subscription_id].copy()

    def save(self, subscription: Subscription) -> None:
        self._subscriptions[subscription.id] = subscription.copy()

    def receipt_for(self, renewal_key: str) -> RenewalReceipt | None:
        return self._receipts.get(renewal_key)

    def save_receipt(self, receipt: RenewalReceipt) -> None:
        self._receipts[receipt.renewal_key] = receipt


class PaymentGateway:
    def __init__(self) -> None:
        self.charges: list[dict[str, object]] = []
        self.decline_next = False

    def charge(self, customer_id: str, amount_cents: int, renewal_key: str) -> None:
        if self.decline_next:
            self.decline_next = False
            raise PaymentDeclined("card declined")
        self.charges.append(
            {"customer_id": customer_id, "amount_cents": amount_cents, "renewal_key": renewal_key}
        )
