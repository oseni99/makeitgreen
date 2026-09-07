"""In-memory ledger storage."""
from __future__ import annotations

import itertools
from threading import RLock
from typing import Any


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for a different logical request."""


class LedgerStore:
    def __init__(self) -> None:
        self.entries: dict[int, dict[str, Any]] = {}
        self.idempotency: dict[str, int] = {}
        self._ids = itertools.count(1)
        self._lock = RLock()

    def add(self, account: str, amount_cents: int, memo: str) -> dict[str, Any]:
        with self._lock:
            return self._add_unlocked(account, amount_cents, memo)

    def _add_unlocked(
        self, account: str, amount_cents: int, memo: str
    ) -> dict[str, Any]:
        entry = {
            "id": next(self._ids),
            "account": account,
            "amount_cents": amount_cents,
            "memo": memo,
        }
        self.entries[entry["id"]] = entry
        return entry

    def create(
        self,
        account: str,
        amount_cents: int,
        memo: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Atomically replay or record a keyed request."""
        with self._lock:
            if idempotency_key is not None:
                existing_id = self.idempotency.get(idempotency_key)
                if existing_id is not None:
                    existing = self.entries[existing_id]
                    if (
                        existing["account"] != account
                        or existing["amount_cents"] != amount_cents
                        or existing["memo"] != memo
                    ):
                        raise IdempotencyConflict
                    return existing

            entry = self._add_unlocked(account, amount_cents, memo)
            if idempotency_key is not None:
                self.idempotency[idempotency_key] = entry["id"]
            return entry

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.entries.values())

    def get(self, entry_id: int) -> dict[str, Any] | None:
        with self._lock:
            return self.entries.get(entry_id)

    def clear(self) -> None:
        with self._lock:
            self.entries.clear()
            self.idempotency.clear()
            self._ids = itertools.count(1)
