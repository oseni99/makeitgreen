# Enrichment timeout incident solution

The evidence shows an optional downstream call returning live data after roughly 300
seconds. Because the handler supplied no deadline, each stalled request held an
in-flight slot for that entire duration until the pool saturated.

The repair passes the documented 750 ms budget to the client and catches only
`DownstreamTimeout` for graceful degradation. Timeout returns the already-available
base results, while unexpected failures remain 500 responses. The existing `finally`
block releases capacity on every path, and genuine capacity exhaustion still sheds load.

In production the deadline must be enforced by the HTTP client itself and should fit
inside the caller's remaining request budget. A fallback is appropriate here only
because enrichment is explicitly optional.
