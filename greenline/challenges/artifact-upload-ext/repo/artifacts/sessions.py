"""Persistence boundary supplied to the upload extension."""
from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


class SessionRepository:
    def __init__(self) -> None:
        self.lock = RLock()
        self._next_id = 1
        self._sessions: dict[str, dict[str, Any]] = {}

    def create(self, state: dict[str, Any]) -> str:
        with self.lock:
            session_id = f"upload-{self._next_id}"
            self._next_id += 1
            stored = deepcopy(state)
            stored["id"] = session_id
            self._sessions[session_id] = stored
            return session_id

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            state = self._sessions.get(session_id)
            return deepcopy(state) if state is not None else None

    def save(self, session_id: str, state: dict[str, Any]) -> None:
        with self.lock:
            if session_id not in self._sessions:
                raise KeyError(session_id)
            self._sessions[session_id] = deepcopy(state)

    def delete(self, session_id: str) -> None:
        with self.lock:
            self._sessions.pop(session_id, None)
