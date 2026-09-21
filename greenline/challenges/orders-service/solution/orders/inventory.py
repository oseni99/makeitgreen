"""Thread-shared inventory for the checkout service."""
from __future__ import annotations

import threading
from collections.abc import Callable


class InsufficientStock(Exception):
    pass


def _allow_reservation(_sku: str) -> None:
    """Default reservation authorization used outside deterministic tests."""


class Inventory:
    def __init__(self, authorize: Callable[[str], None] | None = None) -> None:
        self._stock: dict[str, int] = {}
        self._authorize = authorize if authorize is not None else _allow_reservation
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, sku: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(sku, threading.Lock())

    def add_stock(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        with self._lock_for(sku):
            self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        with self._lock_for(sku):
            return self._stock.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")

        self._authorize(sku)
        with self._lock_for(sku):
            if self._stock.get(sku, 0) < qty:
                raise InsufficientStock(sku)
            self._stock[sku] -= qty

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        with self._lock_for(sku):
            self._stock[sku] = self._stock.get(sku, 0) + qty
