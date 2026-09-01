# Solution

## Root cause

Authentication existed, but direct resource lookup discarded tenant identity. The cache repeated the same mistake by using only the public ticket ID, and mutation had no role check.

## Repair

Move tenant scope into `TicketStore.get_for`, key the cache by `(tenant_id, ticket_id)`, and enforce the agent capability before lookup and mutation. Foreign and missing resources share the same outward result.

## Interview talking points

- Tenant filtering belongs at the narrowest data-access boundary, not only in list routes.
- Cache keys are authorization decisions and must include every isolation dimension.
- Returning the same result for missing and forbidden resources reduces identifier probing.
