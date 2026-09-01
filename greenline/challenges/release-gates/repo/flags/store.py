"""Environment-isolated in-memory gate store."""
from __future__ import annotations

from flags.models import GateDefinition


class GateStore:
    def __init__(self) -> None:
        self._gates: dict[tuple[str, str], GateDefinition] = {}

    def save(self, gate: GateDefinition) -> None:
        self._gates[(gate.environment, gate.key)] = gate

    def get(self, key: str, environment: str) -> GateDefinition | None:
        return self._gates.get((environment, key))
