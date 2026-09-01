"""Per-challenge serialization for workspace and progress mutations."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Iterator


@dataclass
class _Entry:
    lock: Lock = field(default_factory=Lock)
    users: int = 0


_registry_lock = Lock()
_entries: dict[str, _Entry] = {}


def acquire_challenge(slug: str) -> Callable[[], None]:
    """Acquire a challenge lock and return an idempotent release function.

    The explicit lease form lets an HTTP request claim a challenge before a
    background run is submitted, then hand release responsibility to the
    worker. ``threading.Lock`` is intentionally used because ownership is not
    thread-affine.
    """
    with _registry_lock:
        entry = _entries.get(slug)
        if entry is None:
            entry = _Entry()
            _entries[slug] = entry
        entry.users += 1
    entry.lock.acquire()
    released = False

    def release() -> None:
        nonlocal released
        if released:
            return
        released = True
        entry.lock.release()
        with _registry_lock:
            entry.users -= 1
            if entry.users == 0:
                _entries.pop(slug, None)

    return release


@contextmanager
def challenge_operation(slug: str) -> Iterator[None]:
    """Serialize one challenge's mutations without blocking other challenges.

    ``users`` counts both the current owner and queued waiters. Removing an entry
    once that count reaches zero prevents the registry from growing forever as
    new challenge slugs are accessed.
    """
    release = acquire_challenge(slug)
    try:
        yield
    finally:
        release()
