# SRE notes

- Input volume is stable; distinct `service` values are not.
- The worker is intentionally single-pass and cannot replay the source.
- Product accepts estimated counts after cardinality exceeds the configured counter budget.
- `capacity` is an operational hard limit, not a sizing hint.
