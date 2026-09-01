from __future__ import annotations

from copy import deepcopy

from .models import Runbook


class RunbookRepository:
    def __init__(self) -> None:
        self._items: dict[str, Runbook] = {}

    def save(self, runbook: Runbook) -> None:
        self._items[runbook.id] = deepcopy(runbook)

    def get(self, runbook_id: str) -> Runbook:
        return deepcopy(self._items[runbook_id])
