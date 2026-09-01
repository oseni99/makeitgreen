"""Pure, explainable release-gate evaluator."""
from __future__ import annotations

import hashlib
from collections.abc import Collection

from flags.models import EvaluationResult, GateDefinition, Rule


BUCKETS = 10_000


class GateEvaluator:
    def evaluate(self, gate: GateDefinition, context: dict) -> EvaluationResult:
        if gate.disabled:
            return EvaluationResult(False, "disabled")

        workspace_id = context.get("workspace_id")
        if isinstance(workspace_id, str) and workspace_id in gate.allowlist:
            return EvaluationResult(True, "allowlist")

        for rule in gate.rules:
            if self._matches(rule, context):
                return EvaluationResult(rule.value, "rule", rule.rule_id)

        if gate.rollout_percentage > 0:
            if not isinstance(workspace_id, str) or not workspace_id:
                return EvaluationResult(gate.default, "missing_context")
            if self._bucket(gate.key, workspace_id) < gate.rollout_percentage * 100:
                return EvaluationResult(True, "percentage")

        return EvaluationResult(gate.default, "default")

    @staticmethod
    def _matches(rule: Rule, context: dict) -> bool:
        actual = context.get(rule.attribute)
        if rule.operator == "equals":
            return actual == rule.expected
        if rule.operator == "in":
            expected = rule.expected
            return (
                isinstance(expected, Collection)
                and not isinstance(expected, (str, bytes, dict))
                and actual in expected
            )
        raise ValueError(f"unsupported rule operator: {rule.operator}")

    @staticmethod
    def _bucket(gate_key: str, workspace_id: str) -> int:
        digest = hashlib.sha256(f"{gate_key}:{workspace_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big") % BUCKETS
