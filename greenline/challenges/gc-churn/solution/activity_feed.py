from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Event:
    id: str
    created_at: int
    payload: str


def build_feed(
    events: Iterable[Event],
    render: Callable[[Event], dict[str, object]],
    *,
    limit: int = 50,
) -> list[dict[str, object]]:
    if limit < 0:
        raise ValueError("limit must not be negative")
    if limit == 0:
        return []
    selected = heapq.nlargest(limit, events, key=lambda event: (event.created_at, event.id))
    return [render(event) for event in selected]
