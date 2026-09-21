# Flash-sale checkout solution — JavaScript

## Problem summary

The asynchronous checkout path coordinates mutable order state with inventory shared
by overlapping requests. The starter handles ordinary creation and pricing, but each
`await` permits another request to observe and mutate the same logical resource.

## Starter bugs fixed

- Order creation accepted blank SKUs and non-positive unit prices.
- Inventory accepted a zero-sized reservation.
- Reservation checked stock before awaiting authorization, then wrote from stale
  state, allowing several callers to approve the same units.
- Checkout repeated inventory effects when a completed or rejected order was retried.
- Two overlapping calls for one order could both perform the checkout side effect.
- Unexpected authorization errors left the order stuck in `processing`.
- Cancellation accepted orders that never completed, returned no stock, and succeeded
  repeatedly.

## Corrected behavior

Inputs are validated before registration. Authorization completes first; then a
promise-tail mutex for that SKU rechecks and mutates stock atomically. A second
promise-tail mutex serializes lifecycle decisions for each order. Terminal retries
return their existing result, unexpected failures restore `created`, and cancellation
returns stock exactly once for a completed order.

## Edge cases covered

The suite covers blank identities, zero and negative money, zero reservations, exact
discount boundaries, insufficient stock, stock/quantity remainders, independent
SKUs, simultaneous retries, terminal retries, authorization exceptions, invalid
cancellation, and repeated cancellation.

## What to watch for

- JavaScript’s single event-loop thread does not prevent races across `await`.
- One global promise chain preserves correctness but destroys per-SKU parallelism.
- A mutex around only the final write still trusts a stale stock check.
- Checking status before joining the per-order chain leaves simultaneous first calls
  able to proceed together.
- Failing to release a promise tail in `finally` can permanently block later calls.
- Restocking without a lifecycle guard makes repeated cancellation inflate stock.

## Why the fix works

Each promise tail gives operations for one key a stable order while different keys
retain independent chains. Rechecking stock inside the SKU chain removes stale
decisions. Inspecting status and applying side effects inside the order chain makes
retries idempotent. `finally` releases every chain after success or failure.

## Tradeoffs and production considerations

The in-memory chains are process-local and need cleanup for unbounded key counts. A
multi-instance service needs database-backed conditional updates, row locks, or a
reservation ledger, plus a durable idempotency protocol around remote payment work.
Holding a key chain across slow I/O would increase head-of-line blocking, which is why
authorization completes before entering the SKU chain and stock is rechecked inside.

## Interview talking points

- Name the interleaving across `await` as a concurrency race.
- Separate per-order idempotency from per-SKU inventory atomicity.
- Explain the `finally` release and per-key rather than global serialization.
- Discuss how the same invariants move to a database and distributed workers.
