"""Release gate lookup with fixed-default evaluation."""
from __future__ import annotations

from flags.models import EvaluationResult
from flags.store import GateStore


class GateService:
    def __init__(self, store: GateStore) -> None:
        self.store = store

    def evaluate(self, key: str, environment: str, context: dict) -> EvaluationResult:
        gate = self.store.get(key, environment)
        if gate is None:
            return EvaluationResult(False, "missing_gate")
        return EvaluationResult(gate.default, "default")
