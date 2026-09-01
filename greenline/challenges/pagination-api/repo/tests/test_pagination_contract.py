from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pagination import Event, EventPager, EventStore


BASE = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def event(number: int, *, at: datetime | None = None) -> Event:
    return Event(
        id=f"evt-{number}",
        created_at=at or BASE + timedelta(minutes=number),
        message=f"event {number}",
    )


def ids(page: dict) -> list[str]:
    return [item["id"] for item in page["items"]]


def test_page_shape_and_cursor_are_client_opaque() -> None:
    pager = EventPager(EventStore([event(1), event(2), event(3)]))

    page = pager.page(limit=2)

    assert ids(page) == ["evt-3", "evt-2"]
    assert isinstance(page["next_cursor"], str)
    assert "evt-2" not in page["next_cursor"]
    assert page["items"][0]["created_at"].endswith("+00:00")


def test_terminal_page_has_no_next_cursor() -> None:
    pager = EventPager(EventStore([event(1)]))

    page = pager.page(limit=10)

    assert ids(page) == ["evt-1"]
    assert page["next_cursor"] is None


def test_invalid_cursor_is_rejected_cleanly() -> None:
    pager = EventPager(EventStore([event(1)]))

    with pytest.raises(ValueError, match="invalid cursor"):
        pager.page(limit=1, cursor="not-a-valid-cursor")


def test_same_timestamp_uses_id_as_deterministic_tie_breaker() -> None:
    same_time = BASE
    store = EventStore(
        [event(2, at=same_time), event(3, at=same_time), event(1, at=same_time)]
    )

    assert ids(EventPager(store).page(limit=10)) == ["evt-3", "evt-2", "evt-1"]


def test_insertion_between_pages_does_not_shift_the_cursor() -> None:
    store = EventStore([event(number) for number in range(1, 6)])
    pager = EventPager(store)

    first = pager.page(limit=2)
    assert ids(first) == ["evt-5", "evt-4"]

    # This new head record would shift every OFFSET by one.
    store.add(event(6))
    second = pager.page(limit=2, cursor=first["next_cursor"])
    third = pager.page(limit=2, cursor=second["next_cursor"])

    assert ids(second) == ["evt-3", "evt-2"]
    assert ids(third) == ["evt-1"]
    assert third["next_cursor"] is None
