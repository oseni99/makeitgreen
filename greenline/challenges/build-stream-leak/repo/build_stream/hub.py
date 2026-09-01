"""Thread-safe in-process event hub."""
from __future__ import annotations

from collections.abc import Callable
from threading import Lock

EventCallback = Callable[[str, str], None]


class EventHub:
    def __init__(self) -> None:
        self._lock = Lock()
        self._next_token = 1
        self._subscribers: dict[int, EventCallback] = {}

    def subscribe(self, callback: EventCallback) -> int:
        with self._lock:
            token = self._next_token
            self._next_token += 1
            self._subscribers[token] = callback
            return token

    def unsubscribe(self, token: int) -> None:
        with self._lock:
            self._subscribers.pop(token, None)

    def publish(self, build_id: str, event: str) -> None:
        with self._lock:
            callbacks = tuple(self._subscribers.values())
        for callback in callbacks:
            callback(build_id, event)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
