# Solution — audit-export-pool

The service released its connection only after the happy path committed. Permission
denials, query failures, and client cancellation all escaped before rollback and
release, eventually consuming every pool slot.

## Fix

Express the two nested ownership boundaries directly:

1. acquisition is paired with release in an outer `finally`;
2. a begun transaction is paired with commit on success or rollback on failure.

Rollback also handles the driver's failed-transaction state before the connection is
returned. The original exception is then re-raised, preserving the public behavior.

## Why capacity is not the fix

A larger pool changes how many failures are required to trigger the outage. It does not
restore leaked connections, close transactions, or release resources held by an idle
transaction. Correct ownership makes the required capacity proportional to concurrent
work rather than historical errors.

## Interview talking points

- Acquire/release and begin/commit-or-rollback are separate lifecycles.
- Cleanup must cover exceptions raised before a query, during iteration, and after a
  driver has marked a transaction failed.
- Scope-bound cleanup is more reliable than duplicating release calls at each return.
- Lifecycle tests should repeat failures beyond pool capacity and then issue valid work.
