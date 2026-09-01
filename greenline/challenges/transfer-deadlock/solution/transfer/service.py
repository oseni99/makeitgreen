"""Atomic transfers between accounts."""
from __future__ import annotations

import time

from transfer.accounts import AccountStore
from transfer.errors import InsufficientFunds, InvalidAmount


class TransferService:
    def __init__(self, store: AccountStore) -> None:
        self._store = store

    def transfer(self, src: str, dst: str, amount_cents: int) -> None:
        """Move amount_cents from src to dst."""
        if amount_cents <= 0:
            raise InvalidAmount(amount_cents)
        if src == dst:
            raise InvalidAmount(amount_cents)

        first, second = (src, dst) if src < dst else (dst, src)
        with self._store.lock(first):
            time.sleep(0.05)
            with self._store.lock(second):
                if self._store.balance(src) < amount_cents:
                    raise InsufficientFunds(src)
                self._store.debit(src, amount_cents)
                self._store.credit(dst, amount_cents)
