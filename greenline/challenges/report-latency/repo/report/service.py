"""Customer spend report builder."""
from __future__ import annotations

from collections.abc import Sequence

from report.models import Order


def build_customer_report(orders: Sequence[Order]) -> dict[str, dict]:
    """Return per-customer spend totals and order counts.

    Shape:
        {
          "cust-1": {"orders": 2, "spend_cents": 1500, "skus": {"SKU-A": 2}},
          ...
        }
    """
    report: dict[str, dict] = {}
    customer_ids = _unique_customer_ids(orders)
    for customer_id in customer_ids:
        theirs = _orders_for_customer(orders, customer_id)
        spend = 0
        skus: dict[str, int] = {}
        for order in theirs:
            spend += order.total_cents
            skus[order.sku] = skus.get(order.sku, 0) + order.qty
        report[customer_id] = {
            "orders": len(theirs),
            "spend_cents": spend,
            "skus": skus,
        }
    return report


def _unique_customer_ids(orders: Sequence[Order]) -> list[str]:
    seen: list[str] = []
    for order in orders:
        if order.customer_id not in seen:
            seen.append(order.customer_id)
    return seen


def _orders_for_customer(orders: Sequence[Order], customer_id: str) -> list[Order]:
    return [order for order in orders if order.customer_id == customer_id]
