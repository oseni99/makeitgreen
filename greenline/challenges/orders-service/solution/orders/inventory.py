"""SKU stock tracking.

Inventory is shared across checkout worker threads. Reservations must never
allow stock to go below zero.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class InsufficientStock(Exception):
    pass


def _default_authorize(_sku: str) -> None:
    time.sleep(0.001)


class Inventory:
    def __init__(self, authorize: Callable[[str], None] | None = None) -> None:
        self._stock: dict[str, int] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()
        self._authorize = authorize if authorize is not None else _default_authorize

    def _lock_for(self, sku: str) -> threading.Lock:
        # Guard lock creation so two threads can't race a brand-new SKU.
        with self._meta_lock:
            if sku not in self._locks:
                self._locks[sku] = threading.Lock()
            return self._locks[sku]

    def add_stock(self, sku: str, qty: int) -> None:
        with self._lock_for(sku):
            self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        """Reserve qty units of sku, raising InsufficientStock if unavailable."""
        with self._lock_for(sku):
            if self._stock.get(sku, 0) < qty:
                raise InsufficientStock(sku)
            self._authorize(sku)
            self._stock[sku] -= qty
