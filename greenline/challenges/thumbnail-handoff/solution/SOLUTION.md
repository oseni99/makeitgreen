# Thumbnail handoff solution

A condition notification is not stored work. The durable predicate is “items exist or
the queue is closed,” so consumers must check it under the same lock and wait in a loop.
That loop also handles spurious notifications.

Closing sets terminal state while holding the condition and broadcasts to every parked
consumer. Each consumer drains accepted work before returning `None`; later submissions
are rejected. This makes shutdown joinable without polling or timing assumptions.
