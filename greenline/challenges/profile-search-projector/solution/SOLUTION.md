# Profile search projector solution

Allocated change IDs are not commit-order timestamps. The projector now finds the
contiguous visible prefix immediately after its checkpoint and refuses to cross the
first gap. Once the earlier transaction becomes visible, both changes can be consumed.

Projection upserts/deletes and checkpoint advancement execute inside one `BEGIN
IMMEDIATE` transaction. A crash rolls both back, and replay remains safe through
idempotent projection writes.

A PostgreSQL implementation would use a transaction-visibility watermark or an
outbox/commit protocol designed for CDC; merely polling a sequence column cannot prove
that lower IDs will never appear later.
