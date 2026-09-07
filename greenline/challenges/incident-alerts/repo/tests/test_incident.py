"""Post-fix invariants for the 2026-08-29 missed page.

The numbers below mirror logs/incident-2026-08-29.log. Read that file
before hunting through alerting/ — the stack and the SRE replay note
name both failure modes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from alerting.evaluator import evaluate
from alerting.ingest import parse_timestamp
from alerting.models import Rule, Sample
from alerting.service import AlertingService
from alerting.windows import aggregate, samples_in_window

UTC = timezone.utc
INCIDENT_NOW = datetime(2026, 8, 29, 3, 14, 0, tzinfo=UTC)

CHECKOUT_HIGH_ERRORS = Rule(
    name="checkout-high-errors",
    service="checkout-api",
    metric="error_rate",
    threshold=0.50,
    window_seconds=300,
    aggregator="max",
)

# Same scrape the night of the outage. Only 03:14:00 exceeds 0.50.
INCIDENT_SCRAPE = [
    ("checkout-api", "error_rate", 0.08, "2026-08-29T03:10:00Z"),
    ("checkout-api", "error_rate", 0.11, "2026-08-29T03:11:00Z"),
    ("checkout-api", "error_rate", 0.38, "2026-08-29T03:12:00Z"),
    ("checkout-api", "error_rate", 0.44, "2026-08-29T03:13:00Z"),
    ("checkout-api", "error_rate", 0.51, "2026-08-29T03:14:00Z"),
]


def test_aggregate_max_and_avg() -> None:
    samples = [
        Sample("svc", "m", 0.10, INCIDENT_NOW),
        Sample("svc", "m", 0.40, INCIDENT_NOW),
        Sample("svc", "m", 0.25, INCIDENT_NOW),
    ]
    assert aggregate(samples, "max") == 0.40
    assert aggregate(samples, "avg") == pytest.approx(0.25)
    assert aggregate(samples, "last") == 0.25


def test_foreign_service_samples_are_ignored() -> None:
    """A spike on a different service must not trip checkout-high-errors."""
    svc = AlertingService()
    svc.add_rule(CHECKOUT_HIGH_ERRORS)
    svc.ingest("payments-api", "error_rate", 0.99, "2026-08-29T03:13:00Z")
    # Construct the checkout sample with a matching tz so this isn't the
    # timezone bug — it sits strictly inside the window.
    inside = INCIDENT_NOW - timedelta(seconds=60)
    svc.samples.append(Sample("checkout-api", "error_rate", 0.10, inside))
    fired = svc.tick(INCIDENT_NOW)
    assert fired == []


def test_below_threshold_does_not_page() -> None:
    svc = AlertingService()
    svc.add_rule(CHECKOUT_HIGH_ERRORS)
    inside = INCIDENT_NOW - timedelta(seconds=30)
    svc.samples.append(Sample("checkout-api", "error_rate", 0.49, inside))
    assert svc.tick(INCIDENT_NOW) == []


def test_inside_window_max_pages() -> None:
    """A breach strictly inside the window (not on the endpoint) must page."""
    svc = AlertingService()
    svc.add_rule(CHECKOUT_HIGH_ERRORS)
    inside = INCIDENT_NOW - timedelta(seconds=30)
    svc.samples.append(Sample("checkout-api", "error_rate", 0.62, inside))
    fired = svc.tick(INCIDENT_NOW)
    assert len(fired) == 1
    assert fired[0].rule == "checkout-high-errors"
    assert fired[0].value == 0.62


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-08-29T03:14:00Z", INCIDENT_NOW),
        ("2026-08-29T03:14:00+00:00", INCIDENT_NOW),
        ("2026-08-28T22:14:00-05:00", INCIDENT_NOW),
        ("2026-08-29T05:14:00+02:00", INCIDENT_NOW),
    ],
)
def test_offset_timestamp_is_normalized_to_utc(
    raw: str, expected: datetime
) -> None:
    """Scrapers stamp Z. The stored datetime must stay UTC-aware."""
    ts = parse_timestamp(raw)
    assert ts.tzinfo is not None, (
        "Zulu timestamps came back naive — window compares will blow up "
        "against an aware `now` (see logs/traceback.txt)"
    )
    assert ts.utcoffset() == timedelta(0)
    assert ts == expected


@pytest.mark.parametrize(
    "raw",
    ["2026-08-29T03:14:00", "2026-08-29T03:14:00.000", "2026-08-29 03:14:00"],
)
def test_naive_iso_without_z_is_treated_as_utc(raw: str) -> None:
    ts = parse_timestamp(raw)
    assert ts.tzinfo is not None
    assert ts == INCIDENT_NOW


@pytest.mark.parametrize("offset_seconds", [0, 1, 299])
def test_window_includes_sample_at_end(offset_seconds: int) -> None:
    """Evaluation at T must include a sample stamped T. Exclusive end drops it."""
    end = INCIDENT_NOW + timedelta(seconds=offset_seconds)
    start = end - timedelta(seconds=300)
    on_end = Sample("checkout-api", "error_rate", 0.51, end)
    inside = Sample("checkout-api", "error_rate", 0.44, end - timedelta(seconds=60))
    before = Sample("checkout-api", "error_rate", 0.99, start - timedelta(seconds=1))

    window = samples_in_window([before, inside, on_end], start, end)
    assert before not in window
    assert inside in window
    assert on_end in window, (
        "sample at window end (eval now) was dropped — "
        "that's the 03:14:00 point from the SRE replay note"
    )


@pytest.mark.parametrize("aggregator", ["median", "sum", "p99"])
def test_evaluator_does_not_fail_closed_on_bad_rule(aggregator: str) -> None:
    """A broken rule must surface. Swallowing it is a silent missed page."""
    rule = Rule(
        name="broken",
        service="checkout-api",
        metric="error_rate",
        threshold=0.50,
        window_seconds=300,
        aggregator=aggregator,
    )
    samples = [Sample("checkout-api", "error_rate", 0.51, INCIDENT_NOW - timedelta(seconds=10))]
    with pytest.raises(ValueError, match="unknown aggregator"):
        evaluate(rule, samples, INCIDENT_NOW)


def test_incident_replay_pages() -> None:
    """Replay the 03:14Z scrape. checkout-high-errors must fire."""
    svc = AlertingService()
    svc.add_rule(CHECKOUT_HIGH_ERRORS)
    for service, metric, value, ts_raw in INCIDENT_SCRAPE:
        svc.ingest(service, metric, value, ts_raw)

    fired = svc.tick(INCIDENT_NOW)
    assert len(fired) == 1, (
        f"expected a page for checkout-high-errors, got {fired!r} — "
        "read logs/incident-2026-08-29.log and logs/traceback.txt"
    )
    assert fired[0].rule == "checkout-high-errors"
    assert fired[0].service == "checkout-api"
    assert fired[0].value == pytest.approx(0.51)
