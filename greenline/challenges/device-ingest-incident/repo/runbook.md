# Telemetry ingest runbook

- The queue provides at-least-once envelopes with stable event IDs.
- Permanent payload failures are not retryable. Quarantine them and continue.
- Quarantine records must include the event ID, original payload, and classifier reason.
- Infrastructure failures are retryable and must escape the worker so supervision can
  restart it. Never convert an unknown exception into a data-quality rejection.
- Supported metrics are `temperature` and `pressure`; measurements are finite numbers.
