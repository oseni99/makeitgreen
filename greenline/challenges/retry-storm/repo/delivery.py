from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]


class DeliveryRejected(RuntimeError):
    pass


class RetryExhausted(RuntimeError):
    pass


def deliver(
    send: Callable[[], Response],
    sleep: Callable[[float], None],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
) -> Response:
    for _ in range(max_attempts):
        response = send()
        if 200 <= response.status < 300:
            return response
    raise RetryExhausted("delivery attempts exhausted")
