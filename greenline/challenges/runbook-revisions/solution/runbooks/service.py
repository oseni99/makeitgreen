from __future__ import annotations

from .models import Runbook, Snapshot
from .repository import RunbookRepository


class RevisionConflict(RuntimeError):
    pass


class InvalidTransition(RuntimeError):
    pass


class RunbookService:
    ALLOWED = {
        "draft": {"review"},
        "review": {"draft", "approved"},
        "approved": {"active"},
        "active": {"retired"},
        "retired": set(),
    }

    def __init__(self, repository: RunbookRepository) -> None:
        self._repository = repository

    def create(self, runbook_id: str, instructions: list[str]) -> Runbook:
        runbook = Runbook(id=runbook_id, instructions=list(instructions))
        self._append(runbook)
        self._repository.save(runbook)
        return runbook

    def get(self, runbook_id: str) -> Runbook:
        return self._repository.get(runbook_id)

    def edit(self, runbook_id: str, instructions: list[str], expected_revision: int) -> Runbook:
        runbook = self._repository.get(runbook_id)
        self._check_revision(runbook, expected_revision)
        runbook.instructions = list(instructions)
        self._append(runbook)
        self._repository.save(runbook)
        return runbook

    def transition(self, runbook_id: str, target: str, expected_revision: int, *, now: int) -> Runbook:
        runbook = self._repository.get(runbook_id)
        self._check_revision(runbook, expected_revision)
        if target not in self.ALLOWED.get(runbook.state, set()):
            raise InvalidTransition(f"cannot move from {runbook.state} to {target}")
        if target == "active" and runbook.effective_at is not None and now < runbook.effective_at:
            raise InvalidTransition("activation is not due")
        runbook.state = target
        self._append(runbook)
        self._repository.save(runbook)
        return runbook

    def schedule(self, runbook_id: str, effective_at: int, expected_revision: int) -> Runbook:
        runbook = self._repository.get(runbook_id)
        self._check_revision(runbook, expected_revision)
        if runbook.state != "approved":
            raise InvalidTransition("only approved runbooks can be scheduled")
        runbook.effective_at = effective_at
        self._append(runbook)
        self._repository.save(runbook)
        return runbook

    def rollback(self, runbook_id: str, revision: int, expected_revision: int) -> Runbook:
        runbook = self._repository.get(runbook_id)
        self._check_revision(runbook, expected_revision)
        snapshot = next(item for item in runbook.history if item.revision == revision)
        runbook.instructions = list(snapshot.instructions)
        runbook.state = "draft"
        runbook.effective_at = None
        self._append(runbook)
        self._repository.save(runbook)
        return runbook

    @staticmethod
    def _check_revision(runbook: Runbook, expected_revision: int) -> None:
        if runbook.revision != expected_revision:
            raise RevisionConflict(f"expected {expected_revision}, found {runbook.revision}")

    @staticmethod
    def _append(runbook: Runbook) -> None:
        runbook.revision += 1
        runbook.history.append(Snapshot(
            revision=runbook.revision,
            state=runbook.state,
            instructions=tuple(runbook.instructions),
            effective_at=runbook.effective_at,
        ))
