"""Domain objects for the alerting service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Sample:
    service: str
    metric: str
    value: float
    ts: datetime


@dataclass(frozen=True)
class Rule:
    name: str
    service: str
    metric: str
    threshold: float
    window_seconds: int
    aggregator: str  # "avg" | "max" | "last"


@dataclass(frozen=True)
class Page:
    rule: str
    service: str
    value: float
    reason: str
