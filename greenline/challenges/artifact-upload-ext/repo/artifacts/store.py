"""A small content-addressed artifact store."""
from __future__ import annotations

import hashlib
from threading import Lock


class ArtifactStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._objects: dict[str, bytes] = {}

    def put(self, data: bytes) -> str:
        artifact_id = f"sha256:{hashlib.sha256(data).hexdigest()}"
        with self._lock:
            self._objects.setdefault(artifact_id, bytes(data))
        return artifact_id

    def get(self, artifact_id: str) -> bytes:
        with self._lock:
            return self._objects[artifact_id]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._objects)
