"""Domain events carried on the bus."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    payload: dict[str, Any]
