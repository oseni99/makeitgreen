from __future__ import annotations

import gc
import weakref
from threading import Barrier, Thread

import pytest

from build_stream import EventHub, StreamService


def test_active_stream_receives_matching_events_once_and_bounds_history() -> None:
    hub = EventHub()
    stream = StreamService(hub).open("build-7", history_limit=2)
    hub.publish("another-build", "ignored")
    for event in ("queued", "running", "passed"):
        hub.publish("build-7", event)
    assert stream.events == ("running", "passed")
    assert hub.subscriber_count == 1


def test_close_unregisters_and_stops_later_delivery() -> None:
    hub = EventHub()
    service = StreamService(hub)
    stream = service.open("build-7")
    service.close(stream)
    hub.publish("build-7", "late")
    assert stream.events == ()
    assert service.active_count == 0
    assert hub.subscriber_count == 0


def test_closed_streams_are_collectable() -> None:
    hub = EventHub()
    service = StreamService(hub)
    references = []
    for number in range(40):
        stream = service.open(f"build-{number}")
        references.append(weakref.ref(stream))
        service.close(stream)
    del stream
    gc.collect()
    assert hub.subscriber_count == 0
    assert all(reference() is None for reference in references)


def test_close_is_idempotent() -> None:
    hub = EventHub()
    service = StreamService(hub)
    stream = service.open("build-7")
    service.close(stream)
    service.close(stream)
    assert hub.subscriber_count == 0


def test_partial_initialization_releases_subscription() -> None:
    hub = EventHub()
    service = StreamService(hub)
    with pytest.raises(RuntimeError, match="failed to initialize"):
        service.open("build-7", fail_after_subscribe=True)
    assert hub.subscriber_count == 0
    assert service.active_count == 0


def test_publish_can_race_with_close_safely() -> None:
    hub = EventHub()
    service = StreamService(hub)
    stream = service.open("build-7")
    gate = Barrier(2)
    errors: list[BaseException] = []

    def publish() -> None:
        try:
            gate.wait()
            hub.publish("build-7", "finished")
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    worker = Thread(target=publish)
    worker.start()
    gate.wait()
    service.close(stream)
    worker.join()
    assert errors == []
    assert len(stream.events) <= 1
    assert hub.subscriber_count == 0


@pytest.mark.parametrize("stream_count", [1, 2, 8, 32])
def test_every_closed_stream_releases_its_hub_subscription(
    stream_count: int,
) -> None:
    hub = EventHub()
    service = StreamService(hub)
    streams = [service.open(f"build-{number}") for number in range(stream_count)]

    for stream in streams:
        service.close(stream)

    assert service.active_count == 0
    assert hub.subscriber_count == 0


@pytest.mark.parametrize("attempts", [1, 3, 10])
def test_repeated_partial_initialization_never_accumulates_subscribers(
    attempts: int,
) -> None:
    hub = EventHub()
    service = StreamService(hub)

    for number in range(attempts):
        with pytest.raises(RuntimeError, match="failed to initialize"):
            service.open(f"build-{number}", fail_after_subscribe=True)

    assert service.active_count == 0
    assert hub.subscriber_count == 0


def test_closing_one_stream_keeps_other_streams_subscribed() -> None:
    hub = EventHub()
    service = StreamService(hub)
    first = service.open("build-1")
    second = service.open("build-2")

    service.close(first)
    hub.publish("build-2", "running")

    assert first.events == ()
    assert second.events == ("running",)
    assert hub.subscriber_count == 1


def test_closed_stream_can_be_collected_while_an_active_stream_remains() -> None:
    hub = EventHub()
    service = StreamService(hub)
    closed = service.open("closed")
    active = service.open("active")
    reference = weakref.ref(closed)

    service.close(closed)
    del closed
    gc.collect()

    assert reference() is None
    assert service.active_count == 1
    assert hub.subscriber_count == 1
    hub.publish("active", "passed")
    assert active.events == ("passed",)
