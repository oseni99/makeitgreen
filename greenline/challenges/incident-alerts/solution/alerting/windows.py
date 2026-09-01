"""Sliding-window selection and aggregation."""
from __future__ import annotations

from datetime import datetime

from alerting.models import Sample


def samples_in_window(
    samples: list[Sample],
    start: datetime,
    end: datetime,
) -> list[Sample]:
    """Return samples whose ts falls inside [start, end] (inclusive)."""
    return [s for s in samples if start <= s.ts <= end]


def aggregate(samples: list[Sample], how: str) -> float:
    values = [s.value for s in samples]
    if not values:
        raise ValueError("empty window")
    if how == "max":
        return max(values)
    if how == "avg":
        return sum(values) / len(values)
    if how == "last":
        return values[-1]
    raise ValueError(f"unknown aggregator: {how}")
