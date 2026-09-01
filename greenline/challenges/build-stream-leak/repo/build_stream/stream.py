"""Build stream lifecycle. The cleanup path is intentionally incomplete."""
from __future__ import annotations

from collections import deque
from threading import Lock

from .hub import EventHub


class BuildStream:
    def __init__(
        self,
        build_id: str,
        hub: EventHub,
        *,
        history_limit: int = 20,
        fail_after_subscribe: bool = False,
    ) -> None:
        self.build_id = build_id
        self._hub = hub
        self._lock = Lock()
        self._closed = False
        self._events: deque[str] = deque(maxlen=history_limit)
        self._token = hub.subscribe(self._receive)
        if fail_after_subscribe:
            raise RuntimeError("stream sink failed to initialize")

    def _receive(self, build_id: str, event: str) -> None:
        with self._lock:
            if not self._closed and build_id == self.build_id:
                self._events.append(event)

    @property
    def events(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._events)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        # BUG: the hub still owns self._receive and therefore this stream.


class StreamService:
    def __init__(self, hub: EventHub) -> None:
        self._hub = hub
        self._lock = Lock()
        self._active: set[BuildStream] = set()

    def open(self, build_id: str, **options: object) -> BuildStream:
        stream = BuildStream(build_id, self._hub, **options)
        with self._lock:
            self._active.add(stream)
        return stream

    def close(self, stream: BuildStream) -> None:
        stream.close()
        with self._lock:
            self._active.discard(stream)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)
