"""Evaluate a rule against stored samples at a frozen `now`."""
from __future__ import annotations

from datetime import datetime, timedelta

from alerting.models import Page, Rule, Sample
from alerting.windows import aggregate, samples_in_window


def evaluate(rule: Rule, samples: list[Sample], now: datetime) -> Page | None:
    start = now - timedelta(seconds=rule.window_seconds)
    scoped = [
        s
        for s in samples
        if s.service == rule.service and s.metric == rule.metric
    ]
    window = samples_in_window(scoped, start, now)
    if not window:
        return None
    value = aggregate(window, rule.aggregator)
    if value > rule.threshold:
        return Page(
            rule=rule.name,
            service=rule.service,
            value=value,
            reason=f"{rule.aggregator}({rule.metric})={value:.4f} > {rule.threshold}",
        )
    return None
