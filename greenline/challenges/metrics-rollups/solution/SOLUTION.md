# Solution — metrics-rollups

## Root causes

1. Bucket boundaries were anchored to process startup. Two instances started at
   different seconds therefore produced incompatible buckets for identical
   samples.
2. The store compared each sample with the newest timestamp for that metric and
   discarded older points, even when their bucket was still retained.
3. `max_metrics` was accepted by the constructor but never enforced, so attacker
   or tenant-controlled metric names could grow memory without bound.

## Fix

- Align a timestamp by flooring its Unix epoch value to a multiple of
  `bucket_seconds`. For 60-second buckets this always yields `HH:MM:00` UTC.
- Decide lateness against the retention cutoff, not arrival order. Any bucket at
  or after the cutoff remains mutable.
- Reject event timestamps later than the injected clock before creating a
  metric entry, so clock-skewed points cannot distort data or consume quota.
- Prune expired buckets before admission. If a new metric name would exceed
  `max_metrics`, raise `CardinalityLimitExceeded`; samples for existing metrics
  remain accepted. Removing a metric's last expired bucket releases its slot.

The injected aware-UTC clock keeps retention and tests deterministic. Each
metric/bucket accumulator tracks total and count alongside min/max, so average
is calculated without retaining raw samples.

## Interview talking points

- Epoch-aligned buckets let independent processes merge rollups safely.
- Event time and arrival time differ; an explicit lateness/retention policy is
  more reliable than assuming ordered delivery.
- Cardinality is often the dominant metrics-system memory risk. Rejecting new
  names is one policy; eviction, per-tenant quotas, and sketches are alternatives
  with different correctness trade-offs.
- Incremental `(min, max, sum, count)` state is O(metrics × retained buckets),
  while keeping raw points is unbounded in ingest rate.
