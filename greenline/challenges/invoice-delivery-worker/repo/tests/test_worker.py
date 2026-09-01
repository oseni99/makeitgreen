"""Concurrency, acknowledgement, and retry contract for invoice delivery."""
from __future__ import annotations

import threading

import pytest

from invoice_delivery.models import DeliveryCommand, FakeClock
from invoice_delivery.queue import InMemoryQueue
from invoice_delivery.sink import DeliverySink
from invoice_delivery.worker import Worker


def command(message_id: str = "msg-1", invoice_id: str = "inv-1") -> DeliveryCommand:
    return DeliveryCommand(message_id, invoice_id, "ledger@example.test")


def test_successful_delivery_is_acknowledged() -> None:
    queue = InMemoryQueue()
    sink = DeliverySink()
    clock = FakeClock(100)
    queue.publish(command())

    assert Worker(queue, sink, clock).run_one() is True
    assert sink.deliveries == [
        {
            "message_id": "msg-1",
            "invoice_id": "inv-1",
            "destination": "ledger@example.test",
        }
    ]
    assert queue.pending == 0
    assert queue.inflight == 0


def test_transient_failure_waits_for_exponential_retry_time() -> None:
    queue = InMemoryQueue()
    sink = DeliverySink({"inv-1": 1})
    clock = FakeClock(100)
    queue.publish(command())
    worker = Worker(queue, sink, clock)

    assert worker.run_one() is True
    assert queue.next_ready_at() == 101
    assert worker.run_one() is False

    clock.advance(1)
    assert worker.run_one() is True
    assert len(sink.deliveries) == 1


def test_failures_use_one_two_four_eight_then_park() -> None:
    queue = InMemoryQueue()
    sink = DeliverySink({"inv-1": 10})
    clock = FakeClock(0)
    queue.publish(command())
    worker = Worker(queue, sink, clock)

    expected_ready_times = [1, 3, 7, 15]
    for ready_at in expected_ready_times:
        assert worker.run_one() is True
        assert queue.next_ready_at() == ready_at
        clock.advance(ready_at - clock.now())

    assert worker.run_one() is True
    assert queue.pending == 0
    assert queue.inflight == 0
    assert len(queue.parked) == 1
    parked = queue.parked[0]
    assert parked.attempt == 5
    assert len(parked.errors) == 5


def test_delayed_retry_does_not_block_ready_invoice() -> None:
    queue = InMemoryQueue()
    sink = DeliverySink()
    clock = FakeClock(5)
    queue.publish(DeliveryCommand("delayed", "inv-delayed", "a@test", ready_at=20))
    queue.publish(DeliveryCommand("ready", "inv-ready", "b@test", ready_at=5))

    assert Worker(queue, sink, clock).run_one() is True
    assert [item["invoice_id"] for item in sink.deliveries] == ["inv-ready"]
    assert queue.pending == 1


def test_crash_after_effect_leaves_command_for_safe_redelivery() -> None:
    queue = InMemoryQueue()
    sink = DeliverySink()
    clock = FakeClock()
    queue.publish(command())

    def crash() -> None:
        raise RuntimeError("worker crashed before ack")

    with pytest.raises(RuntimeError, match="before ack"):
        Worker(queue, sink, clock, after_delivery=crash).run_one()

    assert queue.inflight == 1
    queue.redeliver_inflight()
    assert Worker(queue, sink, clock).run_one() is True
    assert len(sink.deliveries) == 1
    assert sink.processed_message_ids == {"msg-1"}


def test_two_workers_racing_duplicate_message_produce_one_effect() -> None:
    queue = InMemoryQueue()
    sink = DeliverySink()
    clock = FakeClock()
    queue.publish(command())
    queue.publish(command())
    barrier = threading.Barrier(2)

    def run() -> None:
        barrier.wait()
        Worker(queue, sink, clock).run_one()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(sink.deliveries) == 1
    assert sink.processed_message_ids == {"msg-1"}
    assert queue.pending == 0
    assert queue.inflight == 0
