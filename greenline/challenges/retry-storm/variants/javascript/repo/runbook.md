# Delivery policy

- `maxAttempts` includes the initial transport call.
- Retry only HTTP 429 and 503.
- Honor `Retry-After` when it is a non-negative integer number of seconds.
- Otherwise wait `min(baseDelay * 2 ** retryIndex, maxDelay)`.
- Never sleep after the final allowed attempt.
- Treat every other 4xx/5xx response as a permanent rejection.
