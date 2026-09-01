"""Invoice delivery orchestration."""
from __future__ import annotations

from collections.abc import Callable

from invoice_delivery.models import FakeClock
from invoice_delivery.queue import InMemoryQueue
from invoice_delivery.sink import DeliverySink, TransientDeliveryError


MAX_ATTEMPTS = 5


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

        try:
            self.sink.deliver_once(claim.command)
            if self.after_delivery is not None:
                self.after_delivery()
        except TransientDeliveryError as exc:
            if claim.command.attempt >= MAX_ATTEMPTS:
                self.queue.park(claim, str(exc))
            else:
                delay = 2 ** (claim.command.attempt - 1)
                self.queue.retry(claim, self.clock.now() + delay, str(exc))
            return True

        self.queue.ack(claim)
        return True
