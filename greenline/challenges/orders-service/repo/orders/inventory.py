"""SKU stock tracking.

Inventory is shared across checkout worker threads. Reservations must never
allow stock to go below zero.
"""
from __future__ import annotations

import time


class InsufficientStock(Exception):
    pass


class Inventory:
    def __init__(self) -> None:
        self._stock: dict[str, int] = {}

    def add_stock(self, sku: str, qty: int) -> None:
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        """Reserve qty units of sku, raising InsufficientStock if unavailable."""
        if self._stock.get(sku, 0) < qty:
            raise InsufficientStock(sku)
        # Simulates I/O between the availability check and the write
        # (e.g. a fraud check or payment authorization round-trip).
        time.sleep(0.001)
        self._stock[sku] -= qty
