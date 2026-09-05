# Solution — pagination-api (JavaScript)

The opaque cursor encoded an offset, which is only a position in the current
result. A new head event shifts every remaining position. Encode the last
returned event's complete `(createdAt, id)` ordering key instead, then return
events strictly below that boundary.

The ID tie-breaker makes equal timestamps deterministic. In SQL, this maps to
`ORDER BY created_at DESC, id DESC` and `WHERE (created_at, id) < (?, ?)` with
a matching composite index.
