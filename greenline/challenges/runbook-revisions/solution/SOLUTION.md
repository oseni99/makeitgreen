# Runbook revisions solution

The defects were all violations of the append-only revision contract. `edit` accepted a
stale expected revision, `transition` bypassed the lifecycle map, activation treated the
exact effective time as too early, and rollback replaced history.

The repair checks the caller's revision before every mutation, validates the requested
edge against one transition map, treats `now >= effective_at` as due, and implements
rollback as a new draft snapshot containing the earlier instructions. Existing
snapshots remain immutable tuples, so later edits cannot rewrite the audit trail.

In a database-backed service, the revision comparison and insert would be one
conditional write (for example, `UPDATE ... WHERE revision = ?`) rather than a
process-local read followed by write.
