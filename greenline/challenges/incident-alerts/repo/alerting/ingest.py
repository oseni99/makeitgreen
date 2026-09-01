"""Parse and wrap incoming metric samples."""
from __future__ import annotations

from datetime import datetime

from alerting.models import Sample


def parse_timestamp(raw: str) -> datetime:
    """Parse ISO-8601. Production scrapers emit UTC with a trailing Z."""
    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    # Store naive. The original store had no tz column.
    return dt.replace(tzinfo=None)


def ingest_sample(service: str, metric: str, value: float, ts_raw: str) -> Sample:
    return Sample(service=service, metric=metric, value=value, ts=parse_timestamp(ts_raw))
