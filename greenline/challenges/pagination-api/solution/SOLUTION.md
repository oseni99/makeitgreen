# Solution — pagination-api

## Root cause

The cursor looked opaque, but it only encoded a numeric offset. An offset is a
position in the *current* result set, not an identity-stable boundary. If page
one returned offsets 0–1 and a new event was then inserted at the head, offset
2 pointed at the old second item. The client saw a duplicate and eventually
skipped an older item.

The query also sorted only by `created_at`. Timestamps are not guaranteed to be
unique, so equal-time events had no contractually deterministic order.

## Fix

Use keyset pagination over the complete ordering key:

```python
ordered = sorted(events, key=lambda e: (e.created_at, e.id), reverse=True)
remaining = [e for e in ordered if (e.created_at, e.id) < cursor_boundary]
```

The opaque cursor carries a version plus the last returned event's
`created_at` and `id`. The next request asks for rows strictly below that tuple.
Newer inserts are above the boundary and cannot shift the remaining traversal.
The ID is the deterministic, unique tie-breaker for equal timestamps.

## Interview talking points

- **Offset vs keyset:** offset is convenient for random page numbers, but write
  traffic makes it drift. Keyset pagination is stable and index-friendly for a
  sequential feed.
- **Total ordering matters:** a timestamp alone is not a cursor. Use a unique
  secondary key and match its ascending/descending direction in both `ORDER BY`
  and the boundary predicate.
- **Opaque is not encrypted:** base64 keeps clients from depending on cursor
  internals; sign or encrypt it if tampering or disclosure matters.
- **Cursor evolution:** a version field allows a future encoding or ordering
  change to fail cleanly rather than misread old cursors.
- In SQL this becomes `ORDER BY created_at DESC, id DESC` with
  `WHERE (created_at, id) < (?, ?)` and a matching composite index.
