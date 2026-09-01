"""In-process pub/sub for domain events, with optional webhook fan-out."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from events.models import Event

if TYPE_CHECKING:
    from webhooks.dispatcher import WebhookDispatcher

Handler = Callable[[Event], None]


class EventBus:
    """Fan events out to in-process handlers, then optional webhooks."""

    def __init__(self, webhooks: WebhookDispatcher | None = None) -> None:
        self._handlers: list[Handler] = []
        self._webhooks = webhooks

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers:
            handler(event)
        if self._webhooks is not None:
            self._webhooks.deliver(event)
