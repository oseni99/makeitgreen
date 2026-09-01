from __future__ import annotations

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
    rendered = [(event, render(event)) for event in events]
    rendered.sort(key=lambda pair: (pair[0].created_at, pair[0].id), reverse=True)
    return [row for _, row in rendered[:limit]]
