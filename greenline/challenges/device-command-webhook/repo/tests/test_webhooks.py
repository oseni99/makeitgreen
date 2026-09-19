import importlib

import pytest
from fastapi.testclient import TestClient

module = importlib.import_module("webhooks.app")


def event(delivery_id: str, device: str, sequence: int, state: str) -> dict:
    return {"delivery_id": delivery_id, "device_id": device, "sequence": sequence, "state": state}


def setup_function() -> None:
    module.reset_state()


def test_in_order_results_apply_once() -> None:
    client = TestClient(module.app)
    response = client.post("/webhooks/batch", json={"events": [
        event("d1", "thermostat", 1, "running"),
        event("d2", "thermostat", 2, "succeeded"),
    ]})

    assert response.status_code == 200
    assert response.json()["applied_count"] == 2
    assert client.get("/devices/thermostat").json()["sequence"] == 2


def test_identical_delivery_retry_is_acknowledged_without_an_effect() -> None:
    client = TestClient(module.app)
    payload = event("d1", "thermostat", 1, "running")
    client.post("/webhooks/batch", json={"events": [payload]})

    retry = client.post("/webhooks/batch", json={"events": [payload]})

    assert retry.json() == {"statuses": ["duplicate"], "applied_count": 0}
    assert len(client.get("/devices/thermostat").json()["effects"]) == 1


def test_future_result_is_deferred_then_drained_when_gap_closes() -> None:
    client = TestClient(module.app)
    deferred = client.post("/webhooks/batch", json={"events": [
        event("d2", "thermostat", 2, "succeeded")
    ]})

    assert deferred.json() == {"statuses": ["deferred"], "applied_count": 0}
    assert client.get("/devices/thermostat").status_code == 404

    gap = client.post("/webhooks/batch", json={"events": [
        event("d1", "thermostat", 1, "running")
    ]})
    assert gap.json()["applied_count"] == 2
    assert client.get("/devices/thermostat").json()["state"] == "succeeded"


def test_stale_unique_delivery_is_acknowledged_without_rollback() -> None:
    client = TestClient(module.app)
    client.post("/webhooks/batch", json={"events": [
        event("d1", "thermostat", 1, "running"),
        event("d2", "thermostat", 2, "succeeded"),
    ]})

    stale = client.post("/webhooks/batch", json={"events": [
        event("late-copy", "thermostat", 1, "failed")
    ]})

    assert stale.json() == {"statuses": ["stale"], "applied_count": 0}
    assert client.get("/devices/thermostat").json()["state"] == "succeeded"


def test_devices_advance_independently_inside_one_batch() -> None:
    client = TestClient(module.app)
    result = client.post("/webhooks/batch", json={"events": [
        event("a2", "a", 2, "succeeded"),
        event("b1", "b", 1, "running"),
        event("a1", "a", 1, "running"),
    ]})

    assert result.json()["applied_count"] == 3
    assert client.get("/devices/a").json()["sequence"] == 2
    assert client.get("/devices/b").json()["sequence"] == 1


def test_conflicting_delivery_id_rejects_the_whole_batch() -> None:
    client = TestClient(module.app)
    original = event("same", "a", 1, "running")
    client.post("/webhooks/batch", json={"events": [original]})

    response = client.post("/webhooks/batch", json={"events": [
        event("new", "b", 1, "running"),
        event("same", "a", 1, "failed"),
    ]})

    assert response.status_code == 409
    assert client.get("/devices/b").status_code == 404


@pytest.mark.parametrize("future_sequence", [2, 3, 5])
def test_each_future_sequence_waits_for_its_predecessors(future_sequence: int) -> None:
    client = TestClient(module.app)

    response = client.post(
        "/webhooks/batch",
        json={"events": [event("future", "device", future_sequence, "succeeded")]},
    )

    assert response.json() == {"statuses": ["deferred"], "applied_count": 0}
    assert client.get("/devices/device").status_code == 404


@pytest.mark.parametrize("stale_sequence", [0, 1])
def test_each_stale_sequence_is_ignored_without_state_rollback(
    stale_sequence: int,
) -> None:
    client = TestClient(module.app)
    client.post(
        "/webhooks/batch",
        json={"events": [event("current", "device", 1, "running")]},
    )

    response = client.post(
        "/webhooks/batch",
        json={"events": [event("stale", "device", stale_sequence, "failed")]},
    )

    assert response.json() == {"statuses": ["stale"], "applied_count": 0}
    assert client.get("/devices/device").json()["state"] == "running"


@pytest.mark.parametrize(
    "conflicting",
    [
        event("same", "a", 1, "failed"),
        event("same", "b", 1, "running"),
        event("same", "a", 2, "running"),
    ],
)
def test_delivery_id_conflict_detects_each_fingerprint_field(
    conflicting: dict,
) -> None:
    client = TestClient(module.app)
    client.post(
        "/webhooks/batch",
        json={"events": [event("same", "a", 1, "running")]},
    )

    response = client.post("/webhooks/batch", json={"events": [conflicting]})

    assert response.status_code == 409


def test_conflict_late_in_batch_rolls_back_earlier_events() -> None:
    client = TestClient(module.app)
    client.post(
        "/webhooks/batch",
        json={"events": [event("same", "a", 1, "running")]},
    )

    response = client.post(
        "/webhooks/batch",
        json={
            "events": [
                event("new", "b", 1, "running"),
                event("same", "a", 1, "failed"),
            ]
        },
    )

    assert response.status_code == 409
    assert client.get("/devices/b").status_code == 404
