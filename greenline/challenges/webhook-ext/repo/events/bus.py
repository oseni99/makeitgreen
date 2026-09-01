"""In-process pub/sub for domain events."""
from __future__ import annotations

from collections.abc import Callable

from events.models import Event

Handler = Callable[[Event], None]


class EventBus:
    """Fan events out to in-process handlers.

    Outbound webhooks are intentionally not implemented here — keep HTTP in a
    dedicated package and plug it in via the constructor when you add it.
    """

    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers:
            handler(event)
