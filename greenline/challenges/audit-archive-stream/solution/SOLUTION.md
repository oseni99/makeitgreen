# Audit archive stream solution

The heap snapshot describes bounded writes layered on top of two unbounded
materializations: `list(rows)` and the full formatted-record list. Memory returning at
the end confirms a workload-shaped retention spike rather than a permanent leak.

The repair traverses the forward-only source once, formats into one chunk buffer, writes
when the buffer reaches 128 records, and clears it before continuing. A final partial
buffer is written once. If the sink fails, iteration stops immediately, so the exporter
does not perform unnecessary reads after the failed side effect.

This keeps retained objects proportional to chunk size rather than total export size.
In production the database cursor and upload client must also stream; a bounded loop
cannot compensate for an upstream driver that has already materialized the result set.
