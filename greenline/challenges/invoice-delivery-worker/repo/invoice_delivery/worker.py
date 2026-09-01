"""Invoice delivery orchestration."""
from __future__ import annotations

from collections.abc import Callable

from invoice_delivery.models import FakeClock
from invoice_delivery.queue import InMemoryQueue
from invoice_delivery.sink import DeliverySink, TransientDeliveryError


class Worker:
    def __init__(
        self,
        queue: InMemoryQueue,
        sink: DeliverySink,
        clock: FakeClock,
        *,
        after_delivery: Callable[[], None] | None = None,
    ) -> None:
        self.queue = queue
        self.sink = sink
        self.clock = clock
        self.after_delivery = after_delivery

    def run_one(self) -> bool:
        claim = self.queue.claim_ready(self.clock.now())
        if claim is None:
            return False

        # BUG: acknowledging before the effect creates a loss window, while the
        # unsafe sink repeats effects for duplicate messages.
        self.queue.ack(claim)
        try:
            self.sink.deliver(claim.command)
            if self.after_delivery is not None:
                self.after_delivery()
        except TransientDeliveryError as exc:
            # BUG: immediate, unbounded retries create a hot loop.
            self.queue.publish(claim.command.retry_at(self.clock.now(), str(exc)))
        return True
