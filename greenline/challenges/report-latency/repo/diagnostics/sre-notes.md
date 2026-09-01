# SRE notes — 2026-08-30 report timeout

- Job: `billing.customer_spend_nightly`
- Input size: ~48k orders, ~6k customers
- Wall time before kill: > 120s (SLO is 15s)
- Correctness spot-checks on a 50-order sample still matched finance

## How to read `profiler.txt`

Rows are `cumulative seconds` then `filename:lineno(function)`.
Higher cumulative time = more of the wall clock. Nested calls inflate
callees that are invoked in a loop.

## Working theory

Most of the time sits under `build_customer_report`. One leaf shows up
thousands of times. There is also time in `json.dumps` when the job
serializes the result for S3 — **that path is not the timeout**; it only
runs once at the end.
