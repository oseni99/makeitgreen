from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Change:
    sequence: int
    payload: str


class CDCLog:
    def __init__(self):
        self._changes: list[Change] = []
        self._acked: dict[str, int] = {}
        self._delivered: dict[str, int] = {}
        self._next_sequence = 1

    def append(self, payload: str) -> Change:
        change = Change(self._next_sequence, payload)
        self._next_sequence += 1
        self._changes.append(change)
        return change

    def create_slot(self, name: str) -> None:
        if name in self._acked:
            raise ValueError("slot already exists")
        self._acked[name] = 0
        self._delivered[name] = 0

    def drop_slot(self, name: str) -> None:
        if name not in self._acked:
            raise KeyError(name)
        del self._acked[name]
        del self._delivered[name]

    def poll(self, name: str, limit: int) -> list[Change]:
        if name not in self._acked:
            raise KeyError(name)
        if limit < 0:
            raise ValueError("limit must not be negative")
        changes = [change for change in self._changes if change.sequence > self._acked[name]][:limit]
        if changes:
            self._delivered[name] = max(self._delivered[name], changes[-1].sequence)
        return changes

    def acknowledge(self, name: str, sequence: int) -> None:
        if name not in self._acked:
            raise KeyError(name)
        if sequence < self._acked[name]:
            raise ValueError("acknowledgement cannot move backwards")
        if sequence > self._delivered[name]:
            raise ValueError("cannot acknowledge beyond delivered range")
        self._acked[name] = sequence

    def compact(self) -> int:
        if not self._acked:
            return 0
        floor = min(self._acked.values())
        before = len(self._changes)
        self._changes = [change for change in self._changes if change.sequence > floor]
        return before - len(self._changes)

    @property
    def retained_sequences(self) -> list[int]:
        return [change.sequence for change in self._changes]
