"""Immutable release-gate models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Rule:
    rule_id: str
    attribute: str
    operator: str
    expected: Any
    value: bool


@dataclass(frozen=True)
class GateDefinition:
    key: str
    environment: str
    default: bool = False
    disabled: bool = False
    allowlist: frozenset[str] = field(default_factory=frozenset)
    rules: tuple[Rule, ...] = ()
    rollout_percentage: int = 0

    def __post_init__(self) -> None:
        if not self.key or not self.environment:
            raise ValueError("key and environment are required")
        if not 0 <= self.rollout_percentage <= 100:
            raise ValueError("rollout_percentage must be between 0 and 100")


@dataclass(frozen=True)
class EvaluationResult:
    value: bool
    reason: str
    rule_id: str | None = None
