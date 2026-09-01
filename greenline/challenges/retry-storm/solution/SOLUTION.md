# Solution

## Root cause

The client treated every non-success as transient and retried in a tight loop. It amplified permanent failures, ignored partner backpressure, and made the incident worse.

## Repair

Classify only 429 and 503 as retryable, stop permanent failures immediately, honor valid `Retry-After`, and otherwise use capped exponential delays. Sleep only when another attempt remains.

## Interview talking points

- Production retry policies also need jitter to prevent synchronized clients; deterministic tests omit randomness deliberately.
- Attempt budgets include the initial call.
- Retry classification should be endpoint-specific when a contract makes other statuses safe.
