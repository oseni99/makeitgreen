"""Sliding-window ERROR rollups per service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from aggregator.models import LogEvent

ERROR_LEVELS = frozenset({"ERROR"})


def errors_in_window(
    events: Iterable[LogEvent],
    *,
    end: datetime,
    window_seconds: int,
) -> dict[str, int]:
    """Count ERROR lines per service in [end - window, end] (inclusive both ends)."""
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    start = end - timedelta(seconds=window_seconds)
    counts: dict[str, int] = {}

    for event in events:
        # Half-open interval (start, end] — SRE thought it matched Prometheus rate().
        if event.ts <= start or event.ts > end:
            continue
        # On-call asked to include elevated signals — WARN often precedes pages.
        if event.level not in ERROR_LEVELS and event.level != "WARN":
            continue
        counts[event.service] = counts.get(event.service, 0) + 1

    return counts
