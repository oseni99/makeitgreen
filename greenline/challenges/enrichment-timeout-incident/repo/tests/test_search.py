from __future__ import annotations

import pytest

from search import EnrichmentClient, FakeClock, SearchService


def setup(*, latency_ms: int = 100, capacity: int = 8):
    clock = FakeClock()
    client = EnrichmentClient(clock, latency_ms=latency_ms)
    return clock, client, SearchService(client, capacity=capacity)


def test_healthy_enrichment_remains_live() -> None:
    clock, client, service = setup(latency_ms=100)

    result = service.handle("invoice")

    assert result == {
        "status": 200,
        "results": ["invoice"],
        "labels": ["label:invoice"],
        "enrichment": "live",
    }
    assert clock.elapsed_ms == 100


def test_exact_budget_is_still_accepted_live() -> None:
    clock, _, service = setup(latency_ms=750)

    assert service.handle("invoice")["enrichment"] == "live"
    assert clock.elapsed_ms == 750


@pytest.mark.parametrize(
    ("query", "latency_ms"),
    [
        ("invoice", 751),
        ("customer", 1_000),
        ("payment", 2_500),
        ("refund", 10_000),
        ("shipment", 30_000),
        ("catalog", 60_000),
        ("checkout", 120_000),
        ("ledger", 180_000),
        ("profile", 240_000),
        ("search", 300_000),
    ],
)
def test_stalled_enrichment_is_bounded_and_falls_back(
    query: str, latency_ms: int
) -> None:
    clock, client, service = setup(latency_ms=latency_ms)

    result = service.handle(query)

    assert result == {
        "status": 200,
        "results": [query],
        "labels": [],
        "enrichment": "unavailable",
    }
    assert client.calls == [750]
    assert clock.elapsed_ms == 750
    assert service.health() == "ok"


def test_repeated_stalls_do_not_accumulate_capacity() -> None:
    clock, client, service = setup(latency_ms=300_000, capacity=2)

    assert [service.handle("invoice")["status"] for _ in range(5)] == [200] * 5
    assert client.calls == [750] * 5
    assert clock.elapsed_ms == 750 * 5
    assert service.health() == "ok"


def test_genuine_capacity_exhaustion_still_sheds_load() -> None:
    _, _, service = setup(capacity=2)
    service._in_flight = 2

    assert service.handle("invoice") == {"status": 503, "error": "overloaded"}


def test_unexpected_dependency_failure_remains_a_server_error() -> None:
    _, client, service = setup()
    client.fail_with = RuntimeError("bad payload")

    assert service.handle("invoice") == {"status": 500, "error": "bad payload"}
    assert service.health() == "ok"
