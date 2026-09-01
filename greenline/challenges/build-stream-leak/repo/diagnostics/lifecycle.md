# Expected lifecycle

An open stream owns exactly one event-hub subscription. `close()` may race with a
publisher and may be called repeatedly, but after it returns the subscription must no
longer be retained. If opening fails after subscription, construction must unwind that
ownership before re-raising. A publisher already holding a callback snapshot may call
it once; a closed stream must ignore that callback.
