"""Behavioral specification for the merchandise-return lifecycle."""

import pytest

from returns.errors import DuplicateReturn, InvalidTransition, ReturnNotFound
from returns.service import ReturnService


def test_normal_refund_path_records_ordered_history() -> None:
    service = ReturnService()
    service.open_return("ret-1")

    for state in ("authorized", "received", "inspected", "refunded"):
        service.transition("ret-1", state)

    assert service.state("ret-1") == "refunded"
    assert service.history("ret-1") == [
        {"sequence": 1, "state": "requested"},
        {"sequence": 2, "state": "authorized"},
        {"sequence": 3, "state": "received"},
        {"sequence": 4, "state": "inspected"},
        {"sequence": 5, "state": "refunded"},
    ]


def test_inspection_may_reject_a_return() -> None:
    service = ReturnService()
    service.open_return("ret-2")
    for state in ("authorized", "received", "inspected", "rejected"):
        service.transition("ret-2", state)
    assert service.state("ret-2") == "rejected"


@pytest.mark.parametrize("starting_state", ["requested", "authorized"])
def test_only_early_returns_can_be_cancelled(starting_state: str) -> None:
    service = ReturnService()
    service.open_return("ret-3")
    if starting_state == "authorized":
        service.transition("ret-3", "authorized")
    service.cancel("ret-3")
    assert service.state("ret-3") == "cancelled"


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ([], "received"),
        (["authorized", "received"], "authorized"),
        (["authorized", "received"], "cancelled"),
        (["authorized", "received", "inspected", "refunded"], "requested"),
        (["authorized", "received", "inspected", "rejected"], "refunded"),
    ],
)
def test_invalid_transition_is_an_atomic_no_op(path: list[str], target: str) -> None:
    service = ReturnService()
    service.open_return("ret-4")
    for state in path:
        service.transition("ret-4", state)

    state_before = service.state("ret-4")
    history_before = service.history("ret-4")
    with pytest.raises(InvalidTransition):
        service.transition("ret-4", target)

    assert service.state("ret-4") == state_before
    assert service.history("ret-4") == history_before


def test_repeated_transition_is_rejected() -> None:
    service = ReturnService()
    service.open_return("ret-5")
    with pytest.raises(InvalidTransition):
        service.transition("ret-5", "requested")


def test_unknown_and_duplicate_returns_have_distinct_errors() -> None:
    service = ReturnService()
    with pytest.raises(ReturnNotFound):
        service.state("missing")

    service.open_return("ret-6")
    with pytest.raises(DuplicateReturn):
        service.open_return("ret-6")


def test_listing_is_stable_and_does_not_expose_history() -> None:
    service = ReturnService()
    service.open_return("ret-b")
    service.open_return("ret-a")
    service.transition("ret-b", "authorized")

    assert service.list_returns() == [
        {"id": "ret-a", "state": "requested"},
        {"id": "ret-b", "state": "authorized"},
    ]
