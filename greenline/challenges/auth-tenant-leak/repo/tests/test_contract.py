from support_api import Caller, SupportService, Ticket, TicketStore


def service() -> SupportService:
    return SupportService(TicketStore([
        Ticket("t-1", "north", "North outage"),
        Ticket("t-2", "south", "South invoice"),
    ]))


def test_lists_are_tenant_scoped() -> None:
    assert [ticket.id for ticket in service().list_tickets(Caller("north", "viewer"))] == ["t-1"]


def test_direct_lookup_hides_foreign_ticket() -> None:
    api = service()
    assert api.get_ticket(Caller("north", "viewer"), "t-2") is None


def test_cache_cannot_replay_value_across_tenants() -> None:
    api = service()
    assert api.get_ticket(Caller("south", "agent"), "t-2").title == "South invoice"
    assert api.get_ticket(Caller("north", "agent"), "t-2") is None


def test_viewer_cannot_rename_even_inside_tenant() -> None:
    api = service()
    assert api.rename_ticket(Caller("north", "viewer"), "t-1", "changed") is None
    assert api.get_ticket(Caller("north", "viewer"), "t-1").title == "North outage"


def test_agent_can_rename_own_ticket_and_cache_refreshes() -> None:
    api = service()
    caller = Caller("north", "agent")
    assert api.get_ticket(caller, "t-1").title == "North outage"
    assert api.rename_ticket(caller, "t-1", "Resolved").title == "Resolved"
    assert api.get_ticket(caller, "t-1").title == "Resolved"


def test_agent_cannot_rename_foreign_ticket() -> None:
    api = service()
    assert api.rename_ticket(Caller("north", "agent"), "t-2", "stolen") is None
    assert api.get_ticket(Caller("south", "viewer"), "t-2").title == "South invoice"
