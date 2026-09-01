# Device command webhook solution

Delivery idempotency and device ordering are independent. The repair records an exact
fingerprint for each delivery ID, rejects conflicting reuse, and maintains a separate
last-applied sequence plus deferred map per device.

The handler applies only the next sequence, drains newly contiguous deferred results,
acknowledges stale events without changing state, and processes devices independently.
It works on a copied store and publishes it only after the full batch succeeds, so a
409 cannot leave earlier events in that request partially committed.

A production implementation would enforce the same unit of work in a database
transaction with unique delivery IDs and per-device ordering constraints.
