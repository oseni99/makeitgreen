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


def test_expensive_rendering_is_bounded_by_limit() -> None:
    calls: list[str] = []
    events = (Event(str(index), index, "x" * 1000) for index in range(1000))
    rows = build_feed(events, renderer(calls), limit=10)
    assert len(rows) == 10
    assert len(calls) == 10


def test_zero_limit_does_not_consume_or_render_input() -> None:
    consumed = []
    def events():
        consumed.append(True)
        yield Event("one", 1, "payload")
    calls: list[str] = []
    assert build_feed(events(), renderer(calls), limit=0) == []
    assert consumed == []
    assert calls == []


def test_negative_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="limit"):
        build_feed([], renderer([]), limit=-1)
