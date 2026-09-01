# Solution — cache-ext

This is an **Architecture Extension**: the repository already worked. The new
generic behavior belongs in `cache/`, then the domain repository accepts it
through a narrow optional interface.

## What to add

Create `cache/ttl.py` with `TTLCache(ttl_seconds, clock)`:

- `set(key, value)` stores `(clock() + ttl, value)`;
- `get(key)` returns the value only while `clock() < expires_at` and removes an
  expired entry;
- `delete(key)` invalidates one key;
- reject non-positive TTLs.

The injected monotonic-style clock is the key testing seam. Unit tests advance a
number; production can pass `time.monotonic`. No test sleeps and no expiry test
flakes around wall-clock scheduling.

## Repository wiring

`ProductRepository(cache=None)` preserves every existing caller. On `get`, ask
the cache first; a miss reads backing storage and caches a found product. Both
`save` and `delete` invalidate the SKU so the next read cannot return stale data.
The repository depends on a small `ProductCache` protocol rather than on TTL
implementation details.

## Interview talking points

- **Cache-aside** keeps storage authoritative and makes caching optional.
- Invalidation is usually harder than lookup. Write-through could also work,
  but invalidation keeps one path for reconstructing values from storage.
- `>= expires_at` is expired. Boundary semantics should be explicit and tested.
- This implementation does not negative-cache misses. That avoids ambiguity
  between a missing key and cached `None`; a sentinel or typed result could add
  negative caching later.
- A process-local cache has no cross-instance coherence. Production options
  include versioned keys, event-driven invalidation, or a shared cache, plus
  size bounds/LRU eviction to prevent unbounded memory growth.
