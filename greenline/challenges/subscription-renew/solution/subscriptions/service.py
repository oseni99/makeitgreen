"""Retry-safe, atomic subscription renewal orchestration."""
from __future__ import annotations

from .models import RenewalReceipt, RenewalResult
from .store import PaymentGateway, SubscriptionRepository


class RenewalService:
    PERIOD_SECONDS = 30 * 24 * 60 * 60

    def __init__(self, repository: SubscriptionRepository, gateway: PaymentGateway) -> None:
        self._repository = repository
        self._gateway = gateway

    def renew(self, subscription_id: str, renewal_key: str, now: int) -> RenewalResult:
        existing = self._repository.receipt_for(renewal_key)
        if existing is not None:
            return RenewalResult(renewed=True, receipt=existing)

        subscription = self._repository.get(subscription_id)
        if now < subscription.next_billing_at:
            return RenewalResult(renewed=False, receipt=None)

        subtotal = subscription.unit_price_cents * subscription.seats
        discounted = subtotal * (100 - subscription.discount_percent) // 100
        amount = max(0, discounted - subscription.credit_cents)
        credit_used = min(subscription.credit_cents, discounted)

        # External failure occurs before any durable subscription mutation.
        if amount:
            self._gateway.charge(subscription.customer_id, amount, renewal_key)

        subscription.credit_cents -= credit_used
        subscription.next_billing_at += self.PERIOD_SECONDS
        subscription.status = "active"
        receipt = RenewalReceipt(
            renewal_key=renewal_key,
            subscription_id=subscription.id,
            amount_cents=amount,
            next_billing_at=subscription.next_billing_at,
        )
        self._repository.save(subscription)
        self._repository.save_receipt(receipt)
        return RenewalResult(renewed=True, receipt=receipt)
