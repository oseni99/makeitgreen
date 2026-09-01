from __future__ import annotations

from collections import deque
from threading import Condition, Event
from typing import Generic, TypeVar

T = TypeVar("T")


class ClosedQueue(RuntimeError):
    pass


class HandoffQueue(Generic[T]):
    def __init__(self, *, expected_waiters: int = 0, on_wake: Event | None = None) -> None:
        self._items: deque[T] = deque()
        self._closed = False
        self._condition = Condition()
        self._waiting = 0
        self._expected_waiters = expected_waiters
        self.all_waiting = Event()
        self._on_wake = on_wake

    def put(self, item: T) -> None:
        with self._condition:
            if self._closed:
                raise ClosedQueue("queue is closed")
            self._items.append(item)
            self._condition.notify()

    def get(self) -> T | None:
        with self._condition:
            while not self._items and not self._closed:
                self._waiting += 1
                if self._waiting == self._expected_waiters:
                    self.all_waiting.set()
                self._condition.wait()
                self._waiting -= 1
                if self._on_wake is not None:
                    self._on_wake.set()
            if self._items:
                return self._items.popleft()
            return None

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def poke_all(self) -> None:
        with self._condition:
            self._condition.notify_all()
