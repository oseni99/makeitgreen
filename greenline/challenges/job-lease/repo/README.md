# Job lease store

Run `pytest`. The fake clock makes expiry deterministic. A lease generation
changes whenever ownership changes; stale workers must not mutate the current
lease.
