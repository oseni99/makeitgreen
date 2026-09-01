# outbox-publish

This checkout component uses SQLite and the transactional-outbox pattern:

- `commerce/store.py` owns the schema and SQL operations.
- `commerce/service.py` creates an order and its `order.created` outbox row.
- `commerce/worker.py` polls unpublished rows and calls an injected publisher.

There is no Kafka dependency. Tests provide a deterministic fake publisher and
an injected clock. Run `python -m pytest -v`.

An order without an outbox event is an invalid committed state. Publication is
at-least-once across process crashes, so consumers receive a stable event ID;
within a healthy worker lifecycle, a completed row must not be sent again.
