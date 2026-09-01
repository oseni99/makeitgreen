"""Outbound webhook delivery — keep HTTP out of the event bus."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Protocol

from events.models import Event


class Transport(Protocol):
    def post(self, url: str, body: bytes, headers: dict[str, str]) -> int: ...


class WebhookDispatcher:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._endpoints: list[tuple[str, str]] = []

    def register(self, url: str, secret: str) -> None:
        if not url or not secret:
            raise ValueError("url and secret are required")
        self._endpoints.append((url, secret))

    def deliver(self, event: Event) -> None:
        body = json.dumps(
            {"id": event.id, "type": event.type, "payload": event.payload},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

        for url, secret in self._endpoints:
            signature = hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
            headers = {
                "Content-Type": "application/json",
                "X-Signature": f"sha256={signature}",
            }
            status = self._transport.post(url, body, headers)
            if status >= 500:
                self._transport.post(url, body, headers)
