# Tenant webhook batcher solution

The single global queue caused all three failures. Its length controlled every
tenant's flush boundary, and `splice` removed events before the sender could
confirm delivery.

The fix stores a FIFO queue per tenant, checks `>= maxBatchSize`, snapshots the
next batch with `slice`, and removes it only after `send` returns successfully.
That also isolates failure: an exception for one tenant leaves only that
tenant's queue pending.

In production, the same invariants would need durable storage and a delivery
idempotency key. This exercise intentionally keeps the sender synchronous so
the candidate can focus on batching and acknowledgement semantics.
