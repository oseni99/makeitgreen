"""In-memory account balances with per-account locks."""
from __future__ import annotations

import threading

from transfer.errors import AccountNotFound


class AccountStore:
    def __init__(self) -> None:
        self._balances: dict[str, int] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def open(self, account_id: str, balance_cents: int = 0) -> None:
        with self._meta_lock:
            self._balances[account_id] = balance_cents
            if account_id not in self._locks:
                self._locks[account_id] = threading.Lock()

    def balance(self, account_id: str) -> int:
        if account_id not in self._balances:
            raise AccountNotFound(account_id)
        return self._balances[account_id]

    def lock(self, account_id: str) -> threading.Lock:
        if account_id not in self._locks:
            raise AccountNotFound(account_id)
        return self._locks[account_id]

    def debit(self, account_id: str, amount_cents: int) -> None:
        self._balances[account_id] -= amount_cents

    def credit(self, account_id: str, amount_cents: int) -> None:
        self._balances[account_id] += amount_cents
