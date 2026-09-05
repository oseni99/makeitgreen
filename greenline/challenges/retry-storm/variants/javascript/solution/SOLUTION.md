# Solution — retry-storm (JavaScript)

The client retried every failure in a tight loop. Classify only 429 and 503 as
transient, stop permanent failures immediately, honor valid `Retry-After`, and
otherwise apply capped exponential backoff. Sleep only when another attempt
remains because the attempt budget includes the initial call.

Production retry policies usually add jitter; it is intentionally omitted here
to keep the exercise deterministic.
