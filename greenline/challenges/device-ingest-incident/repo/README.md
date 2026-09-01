# device-ingest-incident

A deterministic telemetry consumer. Each queue envelope has a stable event ID and a
raw JSON payload. Valid measurements update an in-memory device store; permanently
invalid payloads belong in quarantine.

Read the incident evidence before running `python -m pytest -v`.
