"""Thread-shared inventory for the checkout service."""
from __future__ import annotations

from collections.abc import Callable


class InsufficientStock(Exception):
    pass


def _allow_reservation(_sku: str) -> None:
    """Default reservation authorization used outside deterministic tests."""


class Inventory:
    def __init__(self, authorize: Callable[[str], None] | None = None) -> None:
        self._stock: dict[str, int] = {}
        self._authorize = authorize if authorize is not None else _allow_reservation

    def add_stock(self, sku: str, qty: int) -> None:
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        """Reserve units after the configured authorization step."""
        if self._stock.get(sku, 0) < qty:
            raise InsufficientStock(sku)

        # Authorization may yield the thread. Another checkout can change this
        # SKU before the decrement below.
        self._authorize(sku)
        self._stock[sku] -= qty

    def release(self, sku: str, qty: int) -> None:
        self._stock[sku] = self._stock.get(sku, 0) + qty
