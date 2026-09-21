# Flash-sale checkout solution

## Problem summary

The checkout service coordinates mutable order state with inventory shared by worker
threads. The starter handles ordinary creation and pricing, but concurrency, retries,
exceptions, and cancellation can make the order record disagree with available stock.

## Starter bugs fixed

- Order creation accepted blank SKUs and non-positive unit prices.
- Inventory accepted a zero-sized reservation.
- Reservation checked stock before authorization and decremented afterward without
  synchronization, so every waiter could approve the same units.
- Checkout repeated inventory effects when a completed or rejected order was retried.
- Two concurrent calls for one order could both perform the checkout side effect.
- Unexpected authorization errors left the order stuck in `processing`.
- Cancellation accepted orders that never completed, returned no stock, and succeeded
  repeatedly.

## Corrected behavior

Inputs are validated before an order is registered. Authorization happens without
holding an inventory lock; afterward, stock is rechecked and decremented atomically
under a lock dedicated to that SKU. Each order has its own lifecycle lock, so retries
observe the terminal result instead of replaying the side effect. Unexpected failures
restore `created`, while insufficient stock becomes terminal `rejected`. Cancellation
transitions only `completed` orders and releases their stock exactly once.

## Edge cases covered

The suite covers blank identities, zero and negative money, zero reservations, exact
discount boundaries, insufficient stock, several stock/quantity remainders,
independent SKUs, simultaneous retries of one order, repeated completed and rejected
calls, authorization exceptions, cancellation before completion, and repeated
cancellation.

## What to watch for

- A global lock fixes overselling but unnecessarily blocks unrelated SKUs.
- Locking only checkout does not protect direct inventory reservations.
- Checking stock before authorization and locking only the decrement preserves the
  race because the decision was made from stale state.
- Returning early for completed orders without synchronizing the status check still
  lets simultaneous first attempts both proceed.
- Resetting every failure to `created` makes insufficient-stock orders retryable even
  though rejection is part of the terminal contract.
- Restocking before validating cancellation state can duplicate inventory.

## Why the fix works

The SKU lock makes stock validation and mutation one atomic decision while retaining
parallelism between products. The order lock makes lifecycle inspection and side
effects one serialized command per order. Exception-specific transitions keep the
order state aligned with whether inventory changed. Cancellation performs its state
check, release, and transition within the same order critical section.

## Tradeoffs and production considerations

In production, inventory would usually live in a database. An atomic conditional
`UPDATE`, row lock, or reservation ledger would replace the in-memory SKU lock. A
remote payment authorization and a database mutation cannot share a normal process
lock, so a durable idempotency record and compensation workflow would be required.
Per-key locks also need lifecycle management in a long-running service with unbounded
SKU or order cardinality.

## Interview talking points

- Describe the defect as stale check-then-act state, not merely “missing a lock.”
- Separate order idempotency from inventory atomicity; they protect different keys.
- Explain why authorization stays outside the SKU critical section and stock is
  rechecked afterward.
- Map in-memory synchronization to conditional database writes and durable command
  idempotency.
