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
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    for attempt in range(max_attempts):
        response = send()
        if 200 <= response.status < 300:
            return response
        if response.status not in {429, 503}:
            raise DeliveryRejected(f"permanent response {response.status}")
        if attempt == max_attempts - 1:
            break
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            delay = float(retry_after)
        else:
            delay = min(base_delay * (2**attempt), max_delay)
        sleep(delay)
    raise RetryExhausted("delivery attempts exhausted")
