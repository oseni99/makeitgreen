from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Snapshot:
    revision: int
    state: str
    instructions: tuple[str, ...]
    effective_at: int | None


@dataclass
class Runbook:
    id: str
    state: str = "draft"
    revision: int = 0
    instructions: list[str] = field(default_factory=list)
    effective_at: int | None = None
    history: list[Snapshot] = field(default_factory=list)
