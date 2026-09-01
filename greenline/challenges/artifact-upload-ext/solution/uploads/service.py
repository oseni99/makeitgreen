from __future__ import annotations

import hashlib
from typing import Any

from artifacts import ArtifactStore, SessionRepository

from .errors import ChunkConflict, IncompleteUpload, IntegrityError, UploadClosed, UploadNotFound


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class UploadService:
    def __init__(self, store: ArtifactStore, sessions: SessionRepository) -> None:
        self._store = store
        self._sessions = sessions

    def begin(self, name: str, size: int, digest: str) -> str:
        if size < 0:
            raise ValueError("size must be non-negative")
        return self._sessions.create({"name": name, "size": size, "digest": digest, "chunks": {}, "state": "active"})

    def _active(self, session_id: str) -> dict[str, Any]:
        state = self._sessions.get(session_id)
        if state is None:
            raise UploadNotFound(session_id)
        if state["state"] != "active":
            raise UploadClosed(session_id)
        return state

    def put_chunk(self, session_id: str, number: int, data: bytes, digest: str) -> None:
        if number < 1:
            raise ValueError("chunk number must be positive")
        if _digest(data) != digest:
            raise IntegrityError("chunk digest mismatch")
        with self._sessions.lock:
            state = self._active(session_id)
            existing = state["chunks"].get(number)
            chunk = {"data": bytes(data), "digest": digest}
            if existing is not None and existing != chunk:
                raise ChunkConflict(f"chunk {number} already contains different bytes")
            state["chunks"][number] = chunk
            self._sessions.save(session_id, state)

    def status(self, session_id: str) -> dict[str, object]:
        state = self._active(session_id)
        numbers = sorted(state["chunks"])
        return {"received": numbers, "bytes_received": sum(len(state["chunks"][number]["data"]) for number in numbers)}

    def finalize(self, session_id: str, ordered_numbers: list[int]) -> str:
        with self._sessions.lock:
            state = self._active(session_id)
            canonical = list(range(1, len(state["chunks"]) + 1))
            if ordered_numbers != canonical or set(ordered_numbers) != set(state["chunks"]):
                raise IncompleteUpload("chunks must be complete, unique, and in canonical order")
            data = b"".join(state["chunks"][number]["data"] for number in ordered_numbers)
            if len(data) != state["size"]:
                raise IntegrityError("artifact size mismatch")
            if _digest(data) != state["digest"]:
                raise IntegrityError("artifact digest mismatch")
            artifact_id = self._store.put(data)
            state["state"] = "completed"
            state["artifact_id"] = artifact_id
            state["chunks"] = {}
            self._sessions.save(session_id, state)
            return artifact_id

    def cancel(self, session_id: str) -> None:
        self._sessions.delete(session_id)
