"""In-memory merchandise return service."""
from __future__ import annotations

from copy import deepcopy

from returns.errors import DuplicateReturn, InvalidTransition, ReturnNotFound


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "requested": frozenset({"authorized", "cancelled"}),
    "authorized": frozenset({"received", "cancelled"}),
    "received": frozenset({"inspected"}),
    "inspected": frozenset({"refunded", "rejected"}),
    "refunded": frozenset(),
    "rejected": frozenset(),
    "cancelled": frozenset(),
}


class ReturnService:
    def __init__(self) -> None:
        self._returns: dict[str, dict] = {}

    def open_return(self, return_id: str) -> None:
        if return_id in self._returns:
            raise DuplicateReturn(return_id)
        self._returns[return_id] = {
            "id": return_id,
            "state": "requested",
            "history": [{"sequence": 1, "state": "requested"}],
        }

    def transition(self, return_id: str, target: str) -> None:
        record = self._get(return_id)
        current = str(record["state"])
        if target not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransition(current, target)

        record["state"] = target
        record["history"].append(
            {"sequence": len(record["history"]) + 1, "state": target}
        )

    def cancel(self, return_id: str) -> None:
        self.transition(return_id, "cancelled")

    def state(self, return_id: str) -> str:
        return str(self._get(return_id)["state"])

    def history(self, return_id: str) -> list[dict]:
        return deepcopy(self._get(return_id)["history"])

    def list_returns(self) -> list[dict]:
        return [
            {"id": record["id"], "state": record["state"]}
            for record in sorted(self._returns.values(), key=lambda item: item["id"])
        ]

    def _get(self, return_id: str) -> dict:
        try:
            return self._returns[return_id]
        except KeyError as exc:
            raise ReturnNotFound(return_id) from exc
