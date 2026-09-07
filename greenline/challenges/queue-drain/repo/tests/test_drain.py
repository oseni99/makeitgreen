import pytest

from drain_service.drain import drain


@pytest.mark.parametrize(
    "invalid_payload",
    ["not-json", None, [], [1], 42, True, b"bytes"],
    ids=["text", "null", "empty-list", "list", "number", "boolean", "bytes"],
)
def test_poison_event_is_quarantined_and_drain_continues(invalid_payload: object) -> None:
    seen: list[str] = []
    events = [
        {"id": "before", "payload": {"ok": 1}},
        {"id": "bad", "payload": invalid_payload},
        {"id": "after", "payload": {"ok": 2}},
    ]

    processed, quarantined = drain(events, lambda event: seen.append(event["id"]))

    assert processed == ["before", "after"]
    assert quarantined == ["bad"]
    assert seen == ["before", "after"]


def test_processor_failure_is_not_hidden() -> None:
    def fail(_: dict[str, object]) -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        drain([{"id": "a", "payload": {}}], fail)


@pytest.mark.parametrize(
    "message",
    [
        "database constraint",
        "duplicate key",
        "invalid state",
        "downstream rejected",
        "serialization failed",
        "schema mismatch",
        "write conflict",
    ],
)
def test_processor_value_error_is_not_treated_as_bad_input(message: str) -> None:
    def fail(_: dict[str, object]) -> None:
        raise ValueError(message)

    with pytest.raises(ValueError, match=message):
        drain([{"id": "a", "payload": {}}], fail)
