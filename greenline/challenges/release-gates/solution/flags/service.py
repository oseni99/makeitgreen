"""Release gate lookup and deterministic evaluation."""
from __future__ import annotations

from evaluation.evaluator import GateEvaluator
from flags.models import EvaluationResult
from flags.store import GateStore


class GateService:
    def __init__(self, store: GateStore, evaluator: GateEvaluator | None = None) -> None:
        self.store = store
        self.evaluator = evaluator or GateEvaluator()

    def evaluate(self, key: str, environment: str, context: dict) -> EvaluationResult:
        gate = self.store.get(key, environment)
        if gate is None:
            return EvaluationResult(False, "missing_gate")
        return self.evaluator.evaluate(gate, context)
