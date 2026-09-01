from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Caller:
    tenant_id: str
    role: str


@dataclass(frozen=True)
class Ticket:
    id: str
    tenant_id: str
    title: str


class TicketStore:
    def __init__(self, tickets: list[Ticket]):
        self._tickets = {ticket.id: ticket for ticket in tickets}

    def list_for(self, tenant_id: str) -> list[Ticket]:
        return [ticket for ticket in self._tickets.values() if ticket.tenant_id == tenant_id]

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def save(self, ticket: Ticket) -> None:
        self._tickets[ticket.id] = ticket


class SupportService:
    def __init__(self, store: TicketStore):
        self._store = store
        self._cache: dict[str, Ticket] = {}

    def list_tickets(self, caller: Caller) -> list[Ticket]:
        return self._store.list_for(caller.tenant_id)

    def get_ticket(self, caller: Caller, ticket_id: str) -> Ticket | None:
        if ticket_id not in self._cache:
            ticket = self._store.get(ticket_id)
            if ticket is not None:
                self._cache[ticket_id] = ticket
        return self._cache.get(ticket_id)

    def rename_ticket(self, caller: Caller, ticket_id: str, title: str) -> Ticket | None:
        ticket = self._store.get(ticket_id)
        if ticket is None:
            return None
        updated = replace(ticket, title=title)
        self._store.save(updated)
        self._cache[ticket_id] = updated
        return updated
