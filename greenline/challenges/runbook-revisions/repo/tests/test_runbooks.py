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


def test_stale_edit_is_rejected_without_mutating_history() -> None:
    runbooks = service()
    created = runbooks.create("payments", ["restart worker"])
    first = runbooks.edit("payments", ["drain queue"], created.revision)

    with pytest.raises(RevisionConflict):
        runbooks.edit("payments", ["delete database"], created.revision)

    current = runbooks.get("payments")
    assert current.instructions == ["drain queue"]
    assert current.revision == first.revision
    assert len(current.history) == 2


def test_only_legal_lifecycle_transitions_are_accepted() -> None:
    runbooks = service()
    created = runbooks.create("payments", ["restart worker"])

    with pytest.raises(InvalidTransition):
        runbooks.transition("payments", "active", created.revision, now=10)

    assert runbooks.get("payments").state == "draft"


def test_activation_is_allowed_at_exact_scheduled_time() -> None:
    runbooks = service()
    current = runbooks.create("payments", ["restart worker"])
    current = runbooks.transition("payments", "review", current.revision, now=0)
    current = runbooks.transition("payments", "approved", current.revision, now=0)
    current = runbooks.schedule("payments", 100, current.revision)

    with pytest.raises(InvalidTransition):
        runbooks.transition("payments", "active", current.revision, now=99)

    active = runbooks.transition("payments", "active", current.revision, now=100)
    assert active.state == "active"


def test_rollback_appends_a_draft_revision_and_preserves_all_history() -> None:
    runbooks = service()
    first = runbooks.create("payments", ["restart worker"])
    second = runbooks.edit("payments", ["drain queue"], first.revision)
    third = runbooks.edit("payments", ["disable consumer"], second.revision)

    rolled_back = runbooks.rollback("payments", first.revision, third.revision)

    assert rolled_back.instructions == ["restart worker"]
    assert rolled_back.state == "draft"
    assert [item.revision for item in rolled_back.history] == [1, 2, 3, 4]
    assert rolled_back.history[-1].instructions == ("restart worker",)


def test_retired_runbook_is_terminal() -> None:
    runbooks = service()
    current = runbooks.create("payments", ["restart worker"])
    current = runbooks.transition("payments", "review", current.revision, now=0)
    current = runbooks.transition("payments", "approved", current.revision, now=0)
    current = runbooks.transition("payments", "active", current.revision, now=0)
    current = runbooks.transition("payments", "retired", current.revision, now=0)

    with pytest.raises(InvalidTransition):
        runbooks.transition("payments", "draft", current.revision, now=0)
