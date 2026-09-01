"""Ingest log lines and query ERROR rollups."""
from __future__ import annotations

from datetime import datetime

from aggregator.models import LogEvent
from aggregator.parser import parse_line
from aggregator.window import errors_in_window


class LogAggregator:
    def __init__(self) -> None:
        self._events: list[LogEvent] = []

    def ingest(self, line: str) -> LogEvent:
        event = parse_line(line)
        self._events.append(event)
        return event

    def error_counts(self, at: datetime, window_seconds: int) -> dict[str, int]:
        return errors_in_window(
            self._events,
            end=at,
            window_seconds=window_seconds,
        )
