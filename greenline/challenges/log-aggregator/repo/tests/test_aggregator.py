from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aggregator.models import LogEvent
from aggregator.parser import parse_line
from aggregator.service import LogAggregator
from aggregator.window import errors_in_window

UTC = timezone.utc
T0 = datetime(2026, 8, 29, 3, 10, 0, tzinfo=UTC)


def test_parse_line() -> None:
    event = parse_line("2026-08-29T03:10:00Z ERROR checkout-api payment declined")
    assert event.level == "ERROR"
    assert event.service == "checkout-api"
    assert event.message == "payment declined"
    assert event.ts == T0


def test_counts_errors_inside_window() -> None:
    events = [
        LogEvent(T0, "ERROR", "checkout-api", "a"),
        LogEvent(T0.replace(minute=11), "ERROR", "checkout-api", "b"),
        LogEvent(T0.replace(minute=12), "INFO", "checkout-api", "ignored"),
    ]
    counts = errors_in_window(events, end=T0.replace(minute=12), window_seconds=120)
    assert counts == {"checkout-api": 2}


def test_groups_by_service() -> None:
    events = [
        LogEvent(T0, "ERROR", "checkout-api", "a"),
        LogEvent(T0, "ERROR", "payments-api", "b"),
        LogEvent(T0, "ERROR", "checkout-api", "c"),
    ]
    counts = errors_in_window(events, end=T0, window_seconds=60)
    assert counts == {"checkout-api": 2, "payments-api": 1}


def test_ignores_warn_lines() -> None:
    """Only ERROR increments the rollup — WARN is not a page-worthy signal here."""
    events = [
        LogEvent(T0, "ERROR", "checkout-api", "hard fail"),
        LogEvent(T0, "WARN", "checkout-api", "soft fail"),
        LogEvent(T0, "INFO", "checkout-api", "ok"),
    ]
    counts = errors_in_window(events, end=T0, window_seconds=60)
    assert counts == {"checkout-api": 1}


def test_window_includes_start_boundary() -> None:
    """An event exactly at end - window_seconds must be counted."""
    end = datetime(2026, 8, 29, 3, 15, 0, tzinfo=UTC)
    start = datetime(2026, 8, 29, 3, 10, 0, tzinfo=UTC)
    events = [
        LogEvent(start, "ERROR", "checkout-api", "boundary"),
        LogEvent(end, "ERROR", "checkout-api", "at end"),
        LogEvent(start.replace(second=start.second - 1 if start.second else 59), "ERROR", "checkout-api", "too old"),
    ]
    # Fix the "too old" event to be clearly outside the 300s window
    too_old = datetime(2026, 8, 29, 3, 9, 59, tzinfo=UTC)
    events[2] = LogEvent(too_old, "ERROR", "checkout-api", "too old")

    counts = errors_in_window(events, end=end, window_seconds=300)
    assert counts == {"checkout-api": 2}


def test_aggregator_ingest_and_query() -> None:
    agg = LogAggregator()
    agg.ingest("2026-08-29T03:14:00Z ERROR checkout-api timeout")
    agg.ingest("2026-08-29T03:14:30Z WARN checkout-api slow")
    agg.ingest("2026-08-29T03:14:45Z ERROR payments-api declined")

    at = datetime(2026, 8, 29, 3, 15, 0, tzinfo=UTC)
    counts = agg.error_counts(at, window_seconds=60)
    assert counts == {"checkout-api": 1, "payments-api": 1}
