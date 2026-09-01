# SRE incident notes — report-api stall

**2026-08-30 09:14 UTC** — Both report workers busy, request queue depth 0.

**09:15** — Two profile lookups appeared in the executor queue. Active profile
lookups remained 0. Database pool had all connections available.

**09:16** — CPU 0.7%. Memory and file descriptors normal. Adding traffic only
grew the request queue; neither of the first two requests completed.

**09:18** — Thread dump captured. Both `report-worker` threads were parked in
`Future.result()` inside `_build_report`. The futures they awaited were the two
queued profile lookups.

The production pool has two workers. Raising it to four delayed the stall until
four overlapping report requests, so worker count is not the root fix.
