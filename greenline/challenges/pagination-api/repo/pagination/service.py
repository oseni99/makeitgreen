from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Event:
    id: str
    created_at: datetime
    message: str

    def serialize(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class EventStore:
    def __init__(self, events: list[Event] | None = None) -> None:
        self._events = list(events or [])

    def add(self, event: Event) -> None:
        if any(existing.id == event.id for existing in self._events):
            raise ValueError(f"duplicate event id: {event.id}")
        self._events.append(event)

    def all(self) -> list[Event]:
        return list(self._events)


def _encode_offset(offset: int) -> str:
    payload = json.dumps({"offset": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_offset(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        offset = payload["offset"]
        if not isinstance(offset, int) or offset < 0:
            raise ValueError
        return offset
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc


class EventPager:
    def __init__(self, store: EventStore) -> None:
        self._store = store

    def page(self, *, limit: int, cursor: str | None = None) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        # BUG: an offset moves whenever a newer event is inserted. Ordering by
        # timestamp alone is also ambiguous when two events share a timestamp.
        ordered = sorted(
            self._store.all(), key=lambda event: event.created_at, reverse=True
        )
        offset = _decode_offset(cursor) if cursor else 0
        window = ordered[offset : offset + limit]
        next_offset = offset + len(window)
        next_cursor = _encode_offset(next_offset) if next_offset < len(ordered) else None
        return {
            "items": [event.serialize() for event in window],
            "next_cursor": next_cursor,
        }
