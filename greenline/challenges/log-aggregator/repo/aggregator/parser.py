"""Parse structured log lines."""
from __future__ import annotations

from datetime import datetime, timezone

from aggregator.models import LogEvent


def parse_line(line: str) -> LogEvent:
    """Parse `2026-08-29T03:10:00Z LEVEL service message...`."""
    line = line.strip()
    if not line:
        raise ValueError("empty log line")

    ts_raw, level, service, message = line.split(" ", 3)
    if ts_raw.endswith("Z"):
        ts_raw = ts_raw[:-1] + "+00:00"
    ts = datetime.fromisoformat(ts_raw)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return LogEvent(ts=ts, level=level.upper(), service=service, message=message)
