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


def _encode_cursor(event: Event) -> str:
    payload = json.dumps(
        {"v": 1, "created_at": event.created_at.isoformat(), "id": event.id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("v") != 1 or not isinstance(payload.get("id"), str):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        return created_at, payload["id"]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc


class EventPager:
    def __init__(self, store: EventStore) -> None:
        self._store = store

    def page(self, *, limit: int, cursor: str | None = None) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        ordered = sorted(
            self._store.all(),
            key=lambda event: (event.created_at, event.id),
            reverse=True,
        )
        if cursor:
            boundary = _decode_cursor(cursor)
            ordered = [
                event
                for event in ordered
                if (event.created_at, event.id) < boundary
            ]

        window = ordered[:limit]
        next_cursor = (
            _encode_cursor(window[-1]) if len(ordered) > len(window) else None
        )
        return {
            "items": [event.serialize() for event in window],
            "next_cursor": next_cursor,
        }
