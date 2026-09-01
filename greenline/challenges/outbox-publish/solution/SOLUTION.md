# Solution — outbox-publish

## Root cause

`OrderService` wrote the order and event as two independent autocommit
statements. A failure between them left a committed order with no durable event.
It also treated a repeated create command as a fresh insert instead of an
idempotent replay. Separately, `OutboxWorker` published rows but never persisted
`published_at`, so every poll selected and sent the same successful events.

## Fix

- Wrap the existing-order check, order insert, and outbox insert in one
  `BEGIN IMMEDIATE` transaction. Exceptions roll back both writes.
- Use the business order ID as the idempotency boundary and a stable event ID,
  `order.created:<order_id>`. A replay returns the existing order without adding
  another event.
- Mark `published_at` only **after** the publisher succeeds. An exception leaves
  the row pending; a later `run_once` retries it. A marked row is excluded by the
  next poll.

## Interview talking points

- The outbox solves the database/broker dual-write gap by committing business
  state and publish intent in the same database transaction.
- Delivery is still **at least once**: a process can crash after the broker
  accepts an event but before SQLite records `published_at`. Stable event IDs let
  consumers deduplicate that unavoidable replay window.
- Mark-before-publish gives at-most-once behavior and can lose events; mark-after
  gives at-least-once and can duplicate. Payments/order systems usually prefer a
  duplicate they can dedupe over a silently lost event.
- Production workers also need row claiming/leases (`SKIP LOCKED` or equivalent),
  retry backoff, poison-event handling, metrics, and retention/archival.
