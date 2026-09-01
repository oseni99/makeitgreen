# thread-stall

This small report service models the production request dispatcher.

- `reporting/service.py` owns a bounded request pool and assembles reports.
- `diagnostics/threads.txt` is a thread dump captured during the incident.
- `diagnostics/sre-notes.md` contains the incident timeline and pool telemetry.

Start with the diagnostics, then run `python -m pytest -v`.
