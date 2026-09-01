"""Queue and storage models used by the telemetry worker."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Envelope:
    event_id: str
    payload: str


class StateStore:
    def __init__(self) -> None:
        self.devices: dict[str, dict[str, dict[str, float | int]]] = {}
        self.applied_event_ids: list[str] = []
        self._seen: set[str] = set()

    def apply(self, envelope: Envelope, measurement: dict) -> None:
        if envelope.event_id in self._seen:
            return
        device = self.devices.setdefault(measurement["device"], {})
        metric = device.setdefault(measurement["metric"], {"count": 0, "total": 0.0})
        metric["count"] = int(metric["count"]) + 1
        metric["total"] = float(metric["total"]) + float(measurement["value"])
        self._seen.add(envelope.event_id)
        self.applied_event_ids.append(envelope.event_id)


class QuarantineSink:
    def __init__(self) -> None:
        self.records: list[dict[str, str]] = []
        self._seen: set[str] = set()

    def add(self, envelope: Envelope, reason: str) -> None:
        if envelope.event_id in self._seen:
            return
        self._seen.add(envelope.event_id)
        self.records.append(
            {"event_id": envelope.event_id, "payload": envelope.payload, "reason": reason}
        )
