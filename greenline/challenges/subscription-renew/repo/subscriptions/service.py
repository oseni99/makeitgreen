"""Renewal orchestration. Several production edge cases are still broken."""
from __future__ import annotations

from .models import RenewalReceipt, RenewalResult
from .store import PaymentGateway, SubscriptionRepository


class RenewalService:
    PERIOD_SECONDS = 30 * 24 * 60 * 60

    def __init__(self, repository: SubscriptionRepository, gateway: PaymentGateway) -> None:
        self._repository = repository
        self._gateway = gateway

    def renew(self, subscription_id: str, renewal_key: str, now: int) -> RenewalResult:
        subscription = self._repository.get(subscription_id)
        if now <= subscription.next_billing_at:
            return RenewalResult(renewed=False, receipt=None)

        subtotal = subscription.unit_price_cents * subscription.seats
        after_credit = max(0, subtotal - subscription.credit_cents)
        amount = after_credit * (100 - subscription.discount_percent) // 100

        subscription.credit_cents = 0
        subscription.next_billing_at += self.PERIOD_SECONDS
        subscription.status = "active"
        self._repository.save(subscription)

        if amount:
            self._gateway.charge(subscription.customer_id, amount, renewal_key)

        receipt = RenewalReceipt(
            renewal_key=renewal_key,
            subscription_id=subscription.id,
            amount_cents=amount,
            next_billing_at=subscription.next_billing_at,
        )
        self._repository.save_receipt(receipt)
        return RenewalResult(renewed=True, receipt=receipt)
