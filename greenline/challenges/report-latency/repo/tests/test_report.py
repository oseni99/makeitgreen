"""Post-fix invariants for the customer spend report timeout.

Read diagnostics/profiler.txt before changing report/service.py — the dump
names the hot frame (and the red herring).
"""
from __future__ import annotations

import pytest

from report.models import Order
from report.service import build_customer_report


class CountingSequence:
    """Wraps a list and counts how many times callers fully iterate it.

    A single-pass (or two-pass) algorithm touches this a handful of times.
    A per-customer full scan touches it once per customer.
    """

    def __init__(self, items: list[Order]) -> None:
        self._items = items
        self.full_passes = 0

    def __iter__(self):
        self.full_passes += 1
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> Order:
        return self._items[index]


def _order(
    order_id: int,
    customer_id: str,
    sku: str,
    qty: int,
    unit_price_cents: int,
) -> Order:
    return Order(order_id, customer_id, sku, qty, unit_price_cents)


def test_small_report_totals_are_correct() -> None:
    orders = [
        _order(1, "alice", "SKU-A", 2, 100),
        _order(2, "bob", "SKU-B", 1, 500),
        _order(3, "alice", "SKU-A", 1, 100),
        _order(4, "alice", "SKU-C", 3, 50),
    ]
    report = build_customer_report(orders)

    assert report["alice"]["orders"] == 3
    assert report["alice"]["spend_cents"] == 2 * 100 + 1 * 100 + 3 * 50
    assert report["alice"]["skus"] == {"SKU-A": 3, "SKU-C": 3}
    assert report["bob"]["orders"] == 1
    assert report["bob"]["spend_cents"] == 500
    assert report["bob"]["skus"] == {"SKU-B": 1}


def test_empty_input() -> None:
    assert build_customer_report([]) == {}


@pytest.mark.parametrize(
    ("n_customers", "orders_per"),
    [
        (4, 1),
        (5, 2),
        (8, 3),
        (10, 5),
        (12, 4),
        (15, 6),
        (20, 5),
        (25, 8),
        (30, 10),
        (40, 5),
        (50, 10),
        (100, 10),
        (200, 25),
    ],
)
def test_large_report_does_not_rescan_per_customer(
    n_customers: int, orders_per: int
) -> None:
    """Production-sized input: one pass per customer is what burned the SLO.

    The profiler showed ~6k calls into _orders_for_customer, each walking the
    full list. A fixed implementation groups in a constant number of passes.
    """
    items: list[Order] = []
    oid = 1
    for c in range(n_customers):
        cid = f"c-{c}"
        for _ in range(orders_per):
            items.append(_order(oid, cid, f"SKU-{c % 7}", 1, 100))
            oid += 1

    orders = CountingSequence(items)
    report = build_customer_report(orders)

    assert len(report) == n_customers
    assert report["c-0"]["orders"] == orders_per
    assert report["c-0"]["spend_cents"] == orders_per * 100

    # Allow a couple of full passes (e.g. collect ids + aggregate), not one
    # per customer (that would be ~200+).
    assert orders.full_passes <= 3, (
        f"expected ≤3 full passes over orders, got {orders.full_passes} "
        f"(per-customer scans still in play?)"
    )
