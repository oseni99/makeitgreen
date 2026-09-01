"""Existing behavior that the extension must preserve."""

from flags.models import GateDefinition
from flags.service import GateService
from flags.store import GateStore


def test_definitions_are_isolated_by_environment() -> None:
    store = GateStore()
    store.save(GateDefinition("new-search", "development", default=True))
    store.save(GateDefinition("new-search", "production", default=False))

    service = GateService(store)
    assert service.evaluate("new-search", "development", {}).value is True
    assert service.evaluate("new-search", "production", {}).value is False


def test_missing_gate_is_disabled_with_reason() -> None:
    result = GateService(GateStore()).evaluate("missing", "production", {})
    assert result.value is False
    assert result.reason == "missing_gate"
