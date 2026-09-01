# Solution — atomic, tenant-scoped admission

## Root cause

The starter stores every request in one deque, so tenants consume a shared
allowance. It also performs prune → capacity check → append without a lock.
Concurrent callers can all pass the check before any records its admission.

## Fix

- Store one deque per tenant.
- Sample time, prune, check, and append in one critical section so each tenant's
  timestamp deque remains ordered by admission.
- Wait on the injected concurrency probe before acquiring the lock.
- Expire timestamps `<= now - window`, keeping the boundary contract explicit.

## Interview talking points

- This in-process lock is correct for one process, not multiple replicas. A hosted
  limiter needs an atomic shared-store operation or a consistently routed tenant.
- A single lock is simple but can contend across tenants; lock striping is a common
  next step when measurements justify it.
- Decide whether failures should fail open or closed and expose remaining/reset
  metadata at the API boundary.
