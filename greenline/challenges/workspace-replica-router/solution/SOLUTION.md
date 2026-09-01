# Solution — workspace-replica-router

The router needs a dependency, not a global consistency mode. Each successful write
returns the primary commit position and advances only the calling session's watermark.

Before a read, the router compares the replica's applied position with that watermark.
If the replica is available and has applied at least the required position, it is safe;
otherwise the read uses the primary. Equality is sufficient, and once caught up the
session naturally returns to replica offload.

Failed writes never return a commit position and therefore cannot advance the
watermark. Replica availability is checked independently and does not mutate session
state, so recovery immediately restores replica routing.

## Interview talking points

- Read-your-writes is a session guarantee, not global strong consistency.
- A monotonic commit token is more precise than a fixed time-based primary pin.
- Unrelated sessions should retain the scalability benefit of replica reads.
- Point and collection reads must share the same routing policy.
