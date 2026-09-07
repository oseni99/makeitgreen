import pytest

from support_api import Caller, SupportService, Ticket, TicketStore


def service() -> SupportService:
    return SupportService(TicketStore([
        Ticket("n-1", "north", "North outage"),
        Ticket("n-2", "north", "North refund"),
        Ticket("s-1", "south", "South invoice"),
        Ticket("s-2", "south", "South login"),
        Ticket("e-1", "east", "East shipment"),
    ]))


def test_lists_are_tenant_scoped() -> None:
    assert [ticket.id for ticket in service().list_tickets(Caller("north", "viewer"))] == [
        "n-1",
        "n-2",
    ]


@pytest.mark.parametrize(
    ("tenant_id", "ticket_id"),
    [
        ("north", "s-1"),
        ("north", "e-1"),
        ("south", "n-1"),
        ("east", "s-2"),
    ],
)
def test_direct_lookup_hides_foreign_ticket(tenant_id: str, ticket_id: str) -> None:
    assert service().get_ticket(Caller(tenant_id, "viewer"), ticket_id) is None


@pytest.mark.parametrize(
    ("owner_tenant", "foreign_tenant", "ticket_id"),
    [
        ("south", "north", "s-1"),
        ("north", "east", "n-2"),
        ("east", "south", "e-1"),
    ],
)
def test_cache_cannot_replay_value_across_tenants(
    owner_tenant: str,
    foreign_tenant: str,
    ticket_id: str,
) -> None:
    api = service()
    assert api.get_ticket(Caller(owner_tenant, "agent"), ticket_id) is not None
    assert api.get_ticket(Caller(foreign_tenant, "agent"), ticket_id) is None


@pytest.mark.parametrize(
    ("tenant_id", "ticket_id"),
    [("north", "n-1"), ("south", "s-2"), ("east", "e-1")],
)
def test_viewer_cannot_rename_own_ticket(tenant_id: str, ticket_id: str) -> None:
    api = service()
    original = api.get_ticket(Caller(tenant_id, "viewer"), ticket_id)

    assert api.rename_ticket(Caller(tenant_id, "viewer"), ticket_id, "changed") is None
    assert api.get_ticket(Caller(tenant_id, "viewer"), ticket_id) == original


def test_agent_can_rename_own_ticket_and_cache_refreshes() -> None:
    api = service()
    caller = Caller("north", "agent")
    assert api.get_ticket(caller, "n-1").title == "North outage"
    assert api.rename_ticket(caller, "n-1", "Resolved").title == "Resolved"
    assert api.get_ticket(caller, "n-1").title == "Resolved"


@pytest.mark.parametrize(
    ("tenant_id", "ticket_id", "owner_tenant"),
    [
        ("north", "s-1", "south"),
        ("south", "e-1", "east"),
        ("east", "n-2", "north"),
    ],
)
def test_agent_cannot_rename_foreign_ticket(
    tenant_id: str,
    ticket_id: str,
    owner_tenant: str,
) -> None:
    api = service()
    owner = Caller(owner_tenant, "viewer")
    original = api.get_ticket(owner, ticket_id)

    assert api.rename_ticket(Caller(tenant_id, "agent"), ticket_id, "stolen") is None
    assert api.get_ticket(owner, ticket_id) == original
