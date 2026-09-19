"""Behavioral contract for the multi-bug subscription renewal path."""
from __future__ import annotations

import pytest

from subscriptions import (
    PaymentDeclined,
    PaymentGateway,
    RenewalService,
    Subscription,
    SubscriptionRepository,
)

DUE = 1_000_000
PERIOD = RenewalService.PERIOD_SECONDS


def setup_subscription(**changes: object) -> tuple[SubscriptionRepository, PaymentGateway, RenewalService]:
    values: dict[str, object] = {
        "id": "sub-1",
        "customer_id": "cus-1",
        "unit_price_cents": 1_000,
        "seats": 3,
        "discount_percent": 20,
        "credit_cents": 500,
        "next_billing_at": DUE,
    }
    values.update(changes)
    repository = SubscriptionRepository([Subscription(**values)])  # type: ignore[arg-type]
    gateway = PaymentGateway()
    return repository, gateway, RenewalService(repository, gateway)


def test_not_yet_due_is_a_noop() -> None:
    repository, gateway, service = setup_subscription()
    before = repository.get("sub-1")

    result = service.renew("sub-1", "renew-1", DUE - 1)

    assert result.renewed is False
    assert repository.get("sub-1") == before
    assert gateway.charges == []


def test_exact_billing_boundary_is_due() -> None:
    _, gateway, service = setup_subscription(discount_percent=0, credit_cents=0)

    result = service.renew("sub-1", "renew-1", DUE)

    assert result.renewed is True
    assert gateway.charges[0]["amount_cents"] == 3_000


def test_discount_is_applied_before_account_credit() -> None:
    _, gateway, service = setup_subscription()

    result = service.renew("sub-1", "renew-1", DUE)

    assert result.receipt is not None
    assert result.receipt.amount_cents == 1_900  # (3000 * 80%) - 500
    assert gateway.charges[0]["amount_cents"] == 1_900


def test_successful_retry_returns_receipt_without_second_charge() -> None:
    repository, gateway, service = setup_subscription(discount_percent=0, credit_cents=0)
    first = service.renew("sub-1", "renew-1", DUE)
    second = service.renew("sub-1", "renew-1", DUE + PERIOD)

    assert second == first
    assert len(gateway.charges) == 1
    assert repository.get("sub-1").next_billing_at == DUE + PERIOD


def test_decline_does_not_consume_credit_or_advance_billing() -> None:
    repository, gateway, service = setup_subscription()
    before = repository.get("sub-1")
    gateway.decline_next = True

    with pytest.raises(PaymentDeclined, match="declined"):
        service.renew("sub-1", "renew-1", DUE)

    assert repository.get("sub-1") == before
    assert repository.receipt_for("renew-1") is None


def test_declined_key_can_be_retried_successfully() -> None:
    repository, gateway, service = setup_subscription()
    gateway.decline_next = True
    with pytest.raises(PaymentDeclined):
        service.renew("sub-1", "renew-1", DUE)

    result = service.renew("sub-1", "renew-1", DUE)

    assert result.renewed is True
    assert len(gateway.charges) == 1
    assert repository.receipt_for("renew-1") == result.receipt


def test_credit_can_reduce_invoice_to_zero_without_gateway_call() -> None:
    repository, gateway, service = setup_subscription(
        seats=1, discount_percent=50, credit_cents=600
    )

    result = service.renew("sub-1", "renew-free", DUE)

    assert result.receipt is not None
    assert result.receipt.amount_cents == 0
    assert gateway.charges == []
    assert repository.get("sub-1").credit_cents == 100


@pytest.mark.parametrize(
    ("unit_price", "seats", "discount", "credit", "expected"),
    [
        (100, 1, 0, 0, 100),
        (999, 1, 0, 0, 999),
        (500, 2, 10, 0, 900),
        (500, 3, 20, 100, 1100),
        (250, 4, 25, 50, 700),
        (1000, 1, 100, 0, 0),
        (1000, 1, 50, 500, 0),
        (1000, 2, 50, 250, 750),
    ],
)
def test_exact_due_boundary_uses_discount_then_credit_for_pricing_matrix(
    unit_price: int,
    seats: int,
    discount: int,
    credit: int,
    expected: int,
) -> None:
    _, gateway, service = setup_subscription(
        unit_price_cents=unit_price,
        seats=seats,
        discount_percent=discount,
        credit_cents=credit,
    )

    result = service.renew("sub-1", "matrix", DUE)

    assert result.renewed is True
    assert result.receipt is not None
    assert result.receipt.amount_cents == expected
    assert [charge["amount_cents"] for charge in gateway.charges] == (
        [] if expected == 0 else [expected]
    )
