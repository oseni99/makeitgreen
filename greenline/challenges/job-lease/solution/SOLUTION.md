# Solution — job-lease

Renew and release checked only the owner name. Once an expired lease was
reacquired, the old worker still looked like a valid owner and could extend or
delete the new worker's lease.

Fence every mutation with the lease generation as well as the owner. The
generation increments on each acquisition, so a stale lease object can never
mutate a later generation.

This is the same principle used by fenced database leases and distributed job
workers: expiry chooses a new owner, but the generation prevents delayed work
from acting as if it still owns the resource.
