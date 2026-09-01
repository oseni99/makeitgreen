"""Telemetry worker and permanent payload validation."""
from __future__ import annotations

import json
import math

from device_ingest.models import Envelope, QuarantineSink, StateStore


SUPPORTED_METRICS = {"temperature", "pressure"}


class InvalidEvent(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_measurement(payload: str) -> dict:
    try:
        value = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidEvent("invalid_json") from exc
    if not isinstance(value, dict):
        raise InvalidEvent("invalid_json")
    if not isinstance(value.get("device"), str) or not value["device"].strip():
        raise InvalidEvent("missing_device")
    if value.get("metric") not in SUPPORTED_METRICS:
        raise InvalidEvent("unknown_metric")
    measurement = value.get("value")
    if (
        isinstance(measurement, bool)
        or not isinstance(measurement, (int, float))
        or not math.isfinite(float(measurement))
    ):
        raise InvalidEvent("invalid_measurement")
    return value


class Worker:
    def __init__(self, store: StateStore, quarantine: QuarantineSink) -> None:
        self.store = store
        self.quarantine = quarantine

    def run(self, queue: list[Envelope]) -> None:
        while queue:
            current = queue.pop(0)
            try:
                measurement = parse_measurement(current.payload)
            except InvalidEvent as exc:
                self.quarantine.add(current, exc.reason)
                continue
            self.store.apply(current, measurement)
