"""Parse and wrap incoming metric samples."""
from __future__ import annotations

from datetime import datetime, timezone

from alerting.models import Sample


def parse_timestamp(raw: str) -> datetime:
    """Parse ISO-8601 as UTC. A trailing Z or a missing offset both mean UTC."""
    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ingest_sample(service: str, metric: str, value: float, ts_raw: str) -> Sample:
    return Sample(service=service, metric=metric, value=value, ts=parse_timestamp(ts_raw))
