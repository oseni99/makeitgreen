# Tenant rate limiter

`RateLimiter.allow(tenant)` implements a fixed-capacity sliding window. Time is
provided as a callable so callers and tests control the clock. The optional
`decision_gate` coordinates concurrent callers in tests; wait on it before
entering the atomic decision section.

The public contract is encoded in `tests/test_limiter.py`.
