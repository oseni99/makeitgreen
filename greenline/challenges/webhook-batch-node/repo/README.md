# Tenant webhook batcher

`TenantBatcher` accepts events shaped like `{ tenantId, id, payload }`. Each
tenant has an independent FIFO queue. Reaching `maxBatchSize` immediately sends
one batch for that tenant. `flush(tenantId)` sends up to one batch and returns
the number delivered.

The injected sender is synchronous and may throw. A failed delivery must remain
queued in its original order for an identical retry.
