import pytest

from drain_service.drain import drain


def test_poison_event_is_quarantined_and_drain_continues() -> None:
    seen: list[str] = []
    events = [
        {"id": "a", "payload": {"ok": 1}},
        {"id": "bad", "payload": "not-json"},
        {"id": "b", "payload": {"ok": 2}},
    ]
    processed, quarantined = drain(events, lambda event: seen.append(event["id"]))
    assert processed == ["a", "b"]
    assert quarantined == ["bad"]
    assert seen == ["a", "b"]


def test_processor_failure_is_not_hidden() -> None:
    def fail(_: dict[str, object]) -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        drain([{"id": "a", "payload": {}}], fail)


def test_processor_value_error_is_not_treated_as_bad_input() -> None:
    def fail(_: dict[str, object]) -> None:
        raise ValueError("database constraint")

    with pytest.raises(ValueError, match="database constraint"):
        drain([{"id": "a", "payload": {}}], fail)
