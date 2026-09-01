# Solution

## Design

`FlagClient` stores one immutable snapshot per environment with the injected refresh time. It fetches on cold start or TTL expiry, swaps the cache only after a successful fetch, and falls back to an existing snapshot when refresh fails.

## Invariants

- Cold-start failures remain visible because no trustworthy value exists.
- A partial or failed refresh cannot destroy the last-known-good snapshot.
- Environment identity is part of the cache key.
- The injected clock makes expiry behavior deterministic.

## Interview talking points

- A production client may add single-flight refresh, metrics for snapshot age, and a maximum stale age.
- Background refresh trades lower request latency for lifecycle and concurrency complexity.
- Stale fallback is appropriate for availability-oriented flags, but safety-critical kill switches may require a different policy.
