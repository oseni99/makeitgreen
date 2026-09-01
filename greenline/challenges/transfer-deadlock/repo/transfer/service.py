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

        # Lock in transfer direction so the debit/credit pair is easy to read.
        with self._store.lock(src):
            # Simulates reading the source ledger before locking the destination.
            time.sleep(0.05)
            with self._store.lock(dst):
                if self._store.balance(src) < amount_cents:
                    raise InsufficientFunds(src)
                self._store.debit(src, amount_cents)
                self._store.credit(dst, amount_cents)
