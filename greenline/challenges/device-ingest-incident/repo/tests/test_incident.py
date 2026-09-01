"""Regression contract reconstructed from the telemetry incident."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from device_ingest.models import Envelope, QuarantineSink, StateStore
from device_ingest.worker import Worker


def envelope(event_id: str, payload: dict | str) -> Envelope:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return Envelope(event_id, raw)


def incident_queue() -> list[Envelope]:
    fixture = Path(__file__).parents[1] / "fixtures" / "incident.ndjson"
    return [Envelope(**json.loads(line)) for line in fixture.read_text().splitlines()]


def test_incident_fixture_is_drained_and_healthy_events_keep_order() -> None:
    store = StateStore()
    quarantine = QuarantineSink()
    queue = incident_queue()

    Worker(store, quarantine).run(queue)

    assert queue == []
    assert store.applied_event_ids == ["evt-100", "evt-101", "evt-103"]
    assert store.devices == {
        "sensor-a": {"temperature": {"count": 2, "total": 43.5}},
        "sensor-b": {"pressure": {"count": 1, "total": 100.2}},
    }
    assert [(record["event_id"], record["reason"]) for record in quarantine.records] == [
        ("evt-poison-7", "invalid_json"),
        ("evt-102", "unknown_metric"),
    ]


def test_consecutive_invalid_events_are_classified_independently() -> None:
    store = StateStore()
    quarantine = QuarantineSink()
    queue = [
        envelope("bad-json", "{"),
        envelope("no-device", {"metric": "temperature", "value": 4}),
        envelope("bad-metric", {"device": "d-1", "metric": "voltage", "value": 4}),
        envelope("bad-value", {"device": "d-1", "metric": "pressure", "value": "high"}),
        envelope("good", {"device": "d-1", "metric": "pressure", "value": 5}),
    ]

    Worker(store, quarantine).run(queue)

    assert queue == []
    assert [record["reason"] for record in quarantine.records] == [
        "invalid_json",
        "missing_device",
        "unknown_metric",
        "invalid_measurement",
    ]
    assert store.applied_event_ids == ["good"]


def test_redelivered_valid_event_is_applied_once() -> None:
    store = StateStore()
    quarantine = QuarantineSink()
    event = envelope("evt-repeat", {"device": "d-2", "metric": "temperature", "value": 9})

    Worker(store, quarantine).run([event, event])

    assert store.applied_event_ids == ["evt-repeat"]
    assert store.devices["d-2"]["temperature"] == {"count": 1, "total": 9.0}


def test_empty_queue_is_a_no_op() -> None:
    store = StateStore()
    quarantine = QuarantineSink()
    Worker(store, quarantine).run([])
    assert store.devices == {}
    assert quarantine.records == []


def test_unexpected_store_failure_is_not_quarantined() -> None:
    class UnavailableStore(StateStore):
        def apply(self, event: Envelope, measurement: dict) -> None:
            raise RuntimeError("storage unavailable")

    quarantine = QuarantineSink()
    queue = [
        envelope("evt-infra", {"device": "d-3", "metric": "pressure", "value": 1})
    ]
    with pytest.raises(RuntimeError, match="storage unavailable"):
        Worker(UnavailableStore(), quarantine).run(queue)
    assert quarantine.records == []
