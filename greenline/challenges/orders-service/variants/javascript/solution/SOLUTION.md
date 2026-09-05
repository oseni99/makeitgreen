# Solution — orders-service (JavaScript)

## Root cause

`Inventory.reserve()` performs a check-then-act sequence around an `await`.
JavaScript runs each synchronous segment on one event-loop thread, but an
`await` permits other reservations to observe the same stock before any caller
decrements it. All of those callers can then succeed and drive the inventory
negative.

This is still a concurrency race even though it is not a thread race.

## Fix

Serialize the complete check, authorization, and decrement for each SKU. A
promise tail acts as a small per-key mutex: a reservation appends its ticket,
waits for the previous ticket, performs the operation, and always releases its
successor in `finally`.

The lock is per SKU rather than global, so an authorization for `GPU` does not
block an independent `CPU` reservation.

## Tradeoffs

Holding a SKU lock across authorization prioritizes correctness but increases
same-SKU latency. A production service could authorize outside the lock and
then use an atomic conditional database update, compensating when inventory is
gone. That improves throughput but introduces an explicit payment-compensation
workflow.

## Interview talking points

- `await` creates interleavings; single-threaded does not mean race-free.
- Per-key serialization preserves independence between inventory partitions.
- The database equivalent is an atomic `UPDATE ... WHERE stock >= quantity`,
  row locking, or a reservation ledger with a uniqueness constraint.
