"""In-memory fixed-window metric rollups."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone


class CardinalityLimitExceeded(ValueError):
    pass


@dataclass(frozen=True)
class Rollup:
    metric: str
    bucket_start: datetime
    minimum: float
    maximum: float
    average: float
    count: int


@dataclass
class _Accumulator:
    minimum: float
    maximum: float
    total: float
    count: int

    def add(self, value: float) -> None:
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.total += value
        self.count += 1


class MetricRollups:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        bucket_seconds: int = 60,
        retention_buckets: int = 5,
        max_metrics: int = 100,
    ) -> None:
        if bucket_seconds <= 0 or retention_buckets <= 0 or max_metrics <= 0:
            raise ValueError("bucket, retention, and cardinality limits must be positive")
        self._clock = clock
        self._bucket_seconds = bucket_seconds
        self._retention_buckets = retention_buckets
        self._max_metrics = max_metrics
        self._buckets: dict[str, dict[int, _Accumulator]] = {}

    @staticmethod
    def _epoch(value: datetime) -> int:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return int(value.timestamp())

    def _bucket_start(self, timestamp: datetime) -> int:
        epoch = self._epoch(timestamp)
        return (epoch // self._bucket_seconds) * self._bucket_seconds

    def _cutoff(self) -> int:
        current = self._bucket_start(self._clock())
        return current - (self._retention_buckets - 1) * self._bucket_seconds

    def _prune(self) -> None:
        cutoff = self._cutoff()
        for metric, buckets in list(self._buckets.items()):
            self._buckets[metric] = {
                start: acc for start, acc in buckets.items() if start >= cutoff
            }
            if not self._buckets[metric]:
                del self._buckets[metric]

    def ingest(self, metric: str, value: float, timestamp: datetime) -> bool:
        self._prune()
        if self._epoch(timestamp) > self._epoch(self._clock()):
            return False
        start = self._bucket_start(timestamp)
        if start < self._cutoff():
            return False
        if metric not in self._buckets and len(self._buckets) >= self._max_metrics:
            raise CardinalityLimitExceeded(
                f"active metric limit exceeded: max_metrics={self._max_metrics}"
            )

        buckets = self._buckets.setdefault(metric, {})
        acc = buckets.get(start)
        if acc is None:
            buckets[start] = _Accumulator(value, value, value, 1)
        else:
            acc.add(value)
        return True

    def snapshot(self, minutes: int) -> dict[str, list[Rollup]]:
        if not 1 <= minutes <= self._retention_buckets:
            raise ValueError("minutes must be within configured retention")
        self._prune()
        current = self._bucket_start(self._clock())
        cutoff = current - (minutes - 1) * self._bucket_seconds
        result: dict[str, list[Rollup]] = {}
        for metric, buckets in self._buckets.items():
            rows = []
            for start, acc in sorted(buckets.items()):
                if cutoff <= start <= current:
                    rows.append(
                        Rollup(
                            metric=metric,
                            bucket_start=datetime.fromtimestamp(start, timezone.utc),
                            minimum=acc.minimum,
                            maximum=acc.maximum,
                            average=acc.total / acc.count,
                            count=acc.count,
                        )
                    )
            if rows:
                result[metric] = rows
        return result
