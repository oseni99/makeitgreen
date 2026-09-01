# Delivery policy

- A total of `max_attempts` transport calls is allowed.
- Retry only HTTP 429 and 503.
- Use `Retry-After` seconds when it is a valid non-negative integer.
- Otherwise sleep `min(base_delay * 2 ** retry_index, max_delay)` before the next attempt.
- Other 4xx/5xx responses are permanent rejections.
