"""In-memory ledger storage."""
from __future__ import annotations

import itertools
from typing import Any


class LedgerStore:
    def __init__(self) -> None:
        self.entries: dict[int, dict[str, Any]] = {}
        self.idempotency: dict[str, int] = {}
        self._ids = itertools.count(1)

    def add(self, account: str, amount_cents: int, memo: str) -> dict[str, Any]:
        entry = {
            "id": next(self._ids),
            "account": account,
            "amount_cents": amount_cents,
            "memo": memo,
        }
        self.entries[entry["id"]] = entry
        return entry

    def list(self) -> list[dict[str, Any]]:
        return list(self.entries.values())

    def clear(self) -> None:
        self.entries.clear()
        self.idempotency.clear()
        self._ids = itertools.count(1)
