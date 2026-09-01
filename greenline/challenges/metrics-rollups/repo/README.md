# metrics-rollups

`MetricRollups` stores timestamped values in fixed UTC buckets.

## Contract

- Timestamps and the injected `clock()` must be timezone-aware.
- Bucket starts are aligned to Unix-epoch multiples of `bucket_seconds`. A
  60-second bucket always starts at `HH:MM:00`, regardless of process start.
- `retention_buckets=N` retains the current bucket and the preceding `N-1`
  buckets. An older sample is rejected by returning `False`.
- A late sample inside that retained window is accepted, even when newer
  samples for the same metric were already ingested.
- A sample whose event timestamp is later than the injected `clock()` is
  rejected by returning `False`. Rejected future samples store no data and do
  not reserve an active-metric cardinality slot.
- `snapshot(minutes)` returns chronological rollups for the current bucket and
  preceding `minutes-1` buckets. Each metric is isolated and each bucket reports
  `minimum`, `maximum`, `average`, and `count`.
- At most `max_metrics` distinct metric names may have retained samples. A new
  name beyond that limit raises `CardinalityLimitExceeded`; existing names keep
  accepting samples. A name releases its slot after all its buckets expire.

Run tests with `python -m pytest -v`.
