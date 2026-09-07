from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from metrics.rollups import CardinalityLimitExceeded, MetricRollups


NOW = datetime(2026, 8, 30, 12, 5, 37, tzinfo=timezone.utc)


def at(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 8, 30, hour, minute, second, tzinfo=timezone.utc)


def make_store(*, max_metrics: int = 4) -> MetricRollups:
    return MetricRollups(
        clock=lambda: NOW,
        bucket_seconds=60,
        retention_buckets=5,
        max_metrics=max_metrics,
    )


def test_aggregates_min_max_average_and_count() -> None:
    store = make_store()
    assert store.ingest("cpu.load", 4.0, at(12, 3, 40))
    assert store.ingest("cpu.load", 10.0, at(12, 3, 50))
    assert store.ingest("cpu.load", 7.0, at(12, 3, 55))

    [rollup] = store.snapshot(3)["cpu.load"]
    assert rollup.minimum == 4.0
    assert rollup.maximum == 10.0
    assert rollup.average == 7.0
    assert rollup.count == 3


def test_metrics_are_aggregated_independently() -> None:
    store = make_store()
    store.ingest("requests", 12.0, at(12, 5, 20))
    store.ingest("latency", 80.0, at(12, 5, 22))

    snapshot = store.snapshot(1)
    assert snapshot["requests"][0].average == 12.0
    assert snapshot["latency"][0].average == 80.0
    assert snapshot["requests"][0].count == snapshot["latency"][0].count == 1


@pytest.mark.parametrize(
    ("first_second", "second_second"),
    [(1, 59), (5, 40), (20, 58)],
)
def test_buckets_align_to_utc_minute_not_process_start(
    first_second: int, second_second: int
) -> None:
    store = make_store()
    store.ingest("latency", 10.0, at(12, 2, first_second))
    store.ingest("latency", 20.0, at(12, 2, second_second))

    [rollup] = store.snapshot(5)["latency"]
    assert rollup.bucket_start == at(12, 2, 0)
    assert rollup.minimum == 10.0
    assert rollup.maximum == 20.0
    assert rollup.average == 15.0
    assert rollup.count == 2


@pytest.mark.parametrize("late_minute", [2, 3, 4])
def test_late_arrival_inside_retention_updates_older_bucket(
    late_minute: int,
) -> None:
    store = make_store()
    assert store.ingest("errors", 5.0, at(12, 5, 10))
    assert store.ingest("errors", 2.0, at(12, late_minute, 20))

    rows = store.snapshot(6 - late_minute)["errors"]
    assert [(row.bucket_start, row.average) for row in rows] == [
        (at(12, late_minute, 0), 2.0),
        (at(12, 5, 0), 5.0),
    ]


def test_sample_older_than_retention_is_rejected() -> None:
    store = make_store()
    assert not store.ingest("errors", 99.0, at(12, 0, 59))
    assert store.snapshot(5) == {}


@pytest.mark.parametrize("max_metrics", [1, 2, 3])
def test_cardinality_limit_rejects_only_new_metric_names(
    max_metrics: int,
) -> None:
    store = make_store(max_metrics=max_metrics)
    names = [f"metric-{index}" for index in range(max_metrics)]
    for index, name in enumerate(names):
        store.ingest(name, float(index), at(12, 5, index + 1))
    assert store.ingest(names[0], 3.0, at(12, 5, max_metrics + 1))

    with pytest.raises(CardinalityLimitExceeded, match=f"max_metrics={max_metrics}"):
        store.ingest("overflow", 4.0, at(12, 5, max_metrics + 2))


def test_expired_metric_releases_its_cardinality_slot() -> None:
    now = NOW
    store = MetricRollups(
        clock=lambda: now,
        retention_buckets=2,
        max_metrics=1,
    )
    store.ingest("old.metric", 1.0, at(12, 4, 10))
    now = now + timedelta(minutes=2)

    assert store.ingest("new.metric", 2.0, at(12, 7, 5))
    assert set(store.snapshot(1)) == {"new.metric"}


def test_future_sample_is_rejected_without_consuming_cardinality() -> None:
    store = make_store(max_metrics=1)

    assert not store.ingest("future.metric", 99.0, NOW + timedelta(seconds=1))
    assert store.ingest("current.metric", 1.0, NOW)
    assert set(store.snapshot(1)) == {"current.metric"}


def test_naive_timestamps_are_rejected() -> None:
    store = make_store()
    with pytest.raises(ValueError, match="timezone-aware"):
        store.ingest("cpu", 1.0, datetime(2026, 8, 30, 12, 5, 0))
