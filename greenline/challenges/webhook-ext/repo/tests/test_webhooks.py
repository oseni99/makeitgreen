"""Outbound webhook extension — create webhooks/ to make these import."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from events.bus import EventBus
from events.models import Event


class FakeTransport:
    """Test double for HTTP POST. Returns a status code; 500+ means retryable."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []
        self._responses: list[int] = []

    def queue_status(self, *statuses: int) -> None:
        self._responses.extend(statuses)

    def post(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.calls.append((url, body, headers))
        if self._responses:
            return self._responses.pop(0)
        return 200


def _event() -> Event:
    return Event(id="evt-9", type="order.created", payload={"order_id": 42})


def _dispatcher_cls():
    # Imported inside tests so a missing package is a test failure (exit 1),
    # not a collection error (exit 2) — better UX in the workspace RESULTS tab.
    from webhooks.dispatcher import WebhookDispatcher

    return WebhookDispatcher


@pytest.mark.parametrize(
    ("event", "endpoint", "secret"),
    [
        (_event(), "https://hooks.example.test/a", "topsecret"),
        (Event("evt-10", "order.paid", {"order_id": 43}), "https://hooks.example.test/b", "beta"),
        (Event("evt-11", "order.cancelled", {"reason": "fraud"}), "https://hooks.example.test/c", "gamma"),
    ],
)
def test_dispatcher_posts_signed_json_body(
    event: Event, endpoint: str, secret: str
) -> None:
    WebhookDispatcher = _dispatcher_cls()
    transport = FakeTransport()
    hooks = WebhookDispatcher(transport=transport)
    hooks.register(endpoint, secret=secret)

    hooks.deliver(event)

    assert len(transport.calls) == 1
    url, body, headers = transport.calls[0]
    assert url == endpoint
    payload = json.loads(body.decode())
    assert payload == {
        "id": event.id,
        "type": event.type,
        "payload": event.payload,
    }
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert headers.get("X-Signature") == f"sha256={expected}"
    assert headers.get("Content-Type") == "application/json"


def test_bus_publish_fans_out_to_webhooks() -> None:
    WebhookDispatcher = _dispatcher_cls()
    transport = FakeTransport()
    hooks = WebhookDispatcher(transport=transport)
    hooks.register("https://hooks.example.test/a", secret="k")
    bus = EventBus(webhooks=hooks)

    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e.id))
    bus.publish(_event())

    assert seen == ["evt-9"], "in-process handlers must still run"
    assert len(transport.calls) == 1


@pytest.mark.parametrize("status", [500, 502, 503, 599])
def test_retries_once_on_5xx(status: int) -> None:
    WebhookDispatcher = _dispatcher_cls()
    transport = FakeTransport()
    transport.queue_status(status, 200)
    hooks = WebhookDispatcher(transport=transport)
    hooks.register("https://hooks.example.test/a", secret="k")

    hooks.deliver(_event())

    assert len(transport.calls) == 2


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_does_not_retry_on_4xx(status: int) -> None:
    WebhookDispatcher = _dispatcher_cls()
    transport = FakeTransport()
    transport.queue_status(status)
    hooks = WebhookDispatcher(transport=transport)
    hooks.register("https://hooks.example.test/a", secret="k")

    hooks.deliver(_event())

    assert len(transport.calls) == 1


def test_multiple_endpoints_each_get_a_delivery() -> None:
    WebhookDispatcher = _dispatcher_cls()
    transport = FakeTransport()
    hooks = WebhookDispatcher(transport=transport)
    hooks.register("https://hooks.example.test/a", secret="a")
    hooks.register("https://hooks.example.test/b", secret="b")

    hooks.deliver(_event())

    urls = [c[0] for c in transport.calls]
    assert urls == [
        "https://hooks.example.test/a",
        "https://hooks.example.test/b",
    ]
