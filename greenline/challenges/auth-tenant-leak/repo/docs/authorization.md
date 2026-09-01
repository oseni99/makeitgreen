# Authorization contract

- Every read and write is scoped to the caller's `tenant_id`.
- `viewer` and `agent` may read tickets in their tenant.
- Only `agent` may rename a ticket.
- A foreign or missing ticket returns `None`; responses must not reveal cross-tenant existence.
- Cache entries must preserve the same isolation boundary as the backing store.
