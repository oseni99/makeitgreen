"""Existing in-process bus behavior must keep working."""
from __future__ import annotations

from events.bus import EventBus
from events.models import Event


def test_subscribe_and_publish_delivers_to_handlers() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e.type))
    bus.publish(Event(id="e1", type="order.created", payload={"order_id": 1}))
    bus.publish(Event(id="e2", type="order.paid", payload={"order_id": 1}))
    assert seen == ["order.created", "order.paid"]


def test_publish_with_no_subscribers_is_a_noop() -> None:
    bus = EventBus()
    bus.publish(Event(id="e1", type="noop", payload={}))
