"""Parsed log line."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LogEvent:
    ts: datetime
    level: str
    service: str
    message: str
