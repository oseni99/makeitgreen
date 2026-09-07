from __future__ import annotations

import pytest

from runbooks import InvalidTransition, RevisionConflict, RunbookRepository, RunbookService


def service() -> RunbookService:
    return RunbookService(RunbookRepository())


def test_create_and_edit_append_immutable_snapshots() -> None:
    runbooks = service()
    source = ["restart worker"]
    created = runbooks.create("payments", source)
    source.append("page on-call")
    edited = runbooks.edit("payments", ["drain queue"], created.revision)

    assert created.history[0].instructions == ("restart worker",)
    assert [item.instructions for item in edited.history] == [
        ("restart worker",),
        ("drain queue",),
    ]


@pytest.mark.parametrize(
    "stale_instructions",
    [["delete database"], ["skip approval"], ["disable every alert"]],
)
def test_stale_edit_is_rejected_without_mutating_history(
    stale_instructions: list[str],
) -> None:
    runbooks = service()
    created = runbooks.create("payments", ["restart worker"])
    first = runbooks.edit("payments", ["drain queue"], created.revision)

    with pytest.raises(RevisionConflict):
        runbooks.edit("payments", stale_instructions, created.revision)

    current = runbooks.get("payments")
    assert current.instructions == ["drain queue"]
    assert current.revision == first.revision
    assert len(current.history) == 2


@pytest.mark.parametrize("target", ["active", "approved", "retired", "draft"])
def test_only_legal_lifecycle_transitions_are_accepted(target: str) -> None:
    runbooks = service()
    created = runbooks.create("payments", ["restart worker"])

    with pytest.raises(InvalidTransition):
        runbooks.transition("payments", target, created.revision, now=10)

    assert runbooks.get("payments").state == "draft"


@pytest.mark.parametrize("effective_at", [0, 100])
def test_activation_is_allowed_at_exact_scheduled_time(effective_at: int) -> None:
    runbooks = service()
    current = runbooks.create("payments", ["restart worker"])
    current = runbooks.transition("payments", "review", current.revision, now=0)
    current = runbooks.transition("payments", "approved", current.revision, now=0)
    current = runbooks.schedule("payments", effective_at, current.revision)

    with pytest.raises(InvalidTransition):
        runbooks.transition("payments", "active", current.revision, now=effective_at - 1)

    active = runbooks.transition("payments", "active", current.revision, now=effective_at)
    assert active.state == "active"


@pytest.mark.parametrize(
    ("target_revision", "expected_instructions"),
    [(1, ["restart worker"]), (2, ["drain queue"]), (3, ["disable consumer"])],
)
def test_rollback_appends_a_draft_revision_and_preserves_all_history(
    target_revision: int,
    expected_instructions: list[str],
) -> None:
    runbooks = service()
    first = runbooks.create("payments", ["restart worker"])
    second = runbooks.edit("payments", ["drain queue"], first.revision)
    third = runbooks.edit("payments", ["disable consumer"], second.revision)

    rolled_back = runbooks.rollback("payments", target_revision, third.revision)

    assert rolled_back.instructions == expected_instructions
    assert rolled_back.state == "draft"
    assert [item.revision for item in rolled_back.history] == [1, 2, 3, 4]
    assert rolled_back.history[-1].instructions == tuple(expected_instructions)


@pytest.mark.parametrize("target", ["draft", "review"])
def test_retired_runbook_is_terminal(target: str) -> None:
    runbooks = service()
    current = runbooks.create("payments", ["restart worker"])
    current = runbooks.transition("payments", "review", current.revision, now=0)
    current = runbooks.transition("payments", "approved", current.revision, now=0)
    current = runbooks.transition("payments", "active", current.revision, now=0)
    current = runbooks.transition("payments", "retired", current.revision, now=0)

    with pytest.raises(InvalidTransition):
        runbooks.transition("payments", target, current.revision, now=0)
