from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Order:
    id: str
    customer_id: str
    total_cents: int


@dataclass(frozen=True)
class OutboxEvent:
    id: str
    topic: str
    payload: dict[str, Any]
    published_at: str | None
