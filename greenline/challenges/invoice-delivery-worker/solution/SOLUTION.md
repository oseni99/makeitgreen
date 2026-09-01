# Solution — invoice-delivery-worker

The broken worker violated three queue-consumer invariants: it acknowledged before the
effect was safe, used a non-idempotent delivery method, and immediately requeued every
failure without a terminal attempt budget.

## Safe effect and acknowledgement order

`DeliverySink.deliver_once()` commits the message identity and delivery effect under
the same lock. Duplicate commands and a redelivery after a worker crash therefore
become no-ops. The queue acknowledgement happens only after this boundary and the
post-delivery hook complete. A crash before acknowledgement leaves the claim available
for broker-style redelivery.

## Retry policy

The current attempt determines the delay: `2 ** (attempt - 1)` produces 1, 2, 4, and
8 seconds before attempts two through five. The injected clock and `ready_at` field
make this deterministic without sleeping. Failure on attempt five parks the command
with its complete error history instead of circulating again.

## Interview talking points

- At-least-once delivery makes duplicate handling part of the normal success path.
- Acknowledgement defines ownership transfer; doing it early creates message loss.
- Idempotency must be enforced at the effect boundary, not with a process-local check
  separated from the write.
- Delayed items should not occupy a worker or block unrelated ready work.
