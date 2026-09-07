"""SKU stock tracking.

Inventory is shared across checkout worker threads. Reservations must never
allow stock to go below zero.
"""
from __future__ import annotations

import time
from collections.abc import Callable


class InsufficientStock(Exception):
    pass


def _default_authorize(_sku: str) -> None:
    time.sleep(0.001)


class Inventory:
    def __init__(self, authorize: Callable[[str], None] | None = None) -> None:
        self._stock: dict[str, int] = {}
        self._authorize = authorize if authorize is not None else _default_authorize

    def add_stock(self, sku: str, qty: int) -> None:
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        """Reserve qty units of sku, raising InsufficientStock if unavailable."""
        if self._stock.get(sku, 0) < qty:
            raise InsufficientStock(sku)
        self._authorize(sku)
        self._stock[sku] -= qty
