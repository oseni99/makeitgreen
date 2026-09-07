import pytest

from activity_feed import Event, build_feed


def renderer(calls: list[str]):
    def render(event: Event) -> dict[str, object]:
        calls.append(event.id)
        return {"id": event.id, "body": event.payload.upper()}
    return render


def test_returns_newest_events_with_stable_id_tie_break() -> None:
    events = iter([
        Event("b", 10, "second"),
        Event("old", 1, "old"),
        Event("a", 10, "first"),
        Event("new", 20, "new"),
    ])
    rows = build_feed(events, renderer([]), limit=3)
    assert [row["id"] for row in rows] == ["new", "b", "a"]


@pytest.mark.parametrize(
    ("event_count", "limit"),
    [(10, 1), (25, 3), (100, 5), (250, 10), (1_000, 20)],
)
def test_expensive_rendering_is_bounded_by_limit(
    event_count: int, limit: int
) -> None:
    calls: list[str] = []
    events = (Event(str(index), index, "x" * 1000) for index in range(event_count))
    rows = build_feed(events, renderer(calls), limit=limit)
    assert len(rows) == limit
    assert len(calls) == limit


@pytest.mark.parametrize("event_count", [1, 2, 10, 100])
def test_zero_limit_does_not_consume_or_render_input(event_count: int) -> None:
    consumed = []
    def events():
        consumed.append(True)
        for index in range(event_count):
            yield Event(str(index), index, "payload")
    calls: list[str] = []
    assert build_feed(events(), renderer(calls), limit=0) == []
    assert consumed == []
    assert calls == []


@pytest.mark.parametrize("limit", [-1, -2, -10, -50, -1_000])
def test_negative_limit_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        build_feed([], renderer([]), limit=limit)
