# Solution — thread-stall

## Root cause

The thread dump shows both request workers parked in `Future.result()`. Each
worker submitted a profile lookup to **the same two-thread executor** and then
waited synchronously for it. The two lookup jobs are queued, but every worker
that could execute them is occupied by a request waiting for a lookup.

This is thread-pool starvation (often called sync-over-async starvation), not
a two-lock deadlock. The timeout makes the symptom recover eventually; it does
not make the dependency graph safe.

## Fix

The profile loader is a synchronous dependency, so call it directly inside the
request worker. The bounded pool still limits concurrent requests, but no
request enqueues work that requires another slot in that same pool.

An alternative in a larger system is a genuinely separate dependency executor
with independently justified capacity and backpressure. Increasing this pool's
worker count only moves the saturation threshold.

## Interview talking points

- Start from evidence: low CPU plus workers waiting on futures suggests blocked
  work, while the queue reveals the circular executor dependency.
- Distinguish pool starvation from lock deadlock: no pair of locks is acquired
  in opposite order; progress depends on a worker slot that cannot become free.
- Timeouts bound impact and aid recovery, but are not the correctness fix.
- Discuss backpressure, separate bulkheads, queue metrics, active-worker gauges,
  and avoiding blocking waits inside event-loop or executor callbacks.
