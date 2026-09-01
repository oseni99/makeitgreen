# Digest scheduler solution

Claiming was a check-then-write race, so both workers could observe an eligible job.
The repair runs eligibility and lease assignment under one store lock. Every reclaim
increments a fencing generation.

Execution and completion now require matching owner and generation plus a lease whose
deadline is strictly in the future. A stale attempt therefore fails before delivery.
Completed jobs are terminal and cannot be reclaimed.

A production scheduler would enforce these comparisons in conditional database writes
and make the delivery side effect idempotent. A process lock demonstrates the invariant
but is not distributed coordination.
