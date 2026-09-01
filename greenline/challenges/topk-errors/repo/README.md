# Error heavy hitters

The worker consumes `(service, level)` events once and exposes `topk()`. Production
evidence is in `diagnostics/`. The configured `capacity` is a hard state bound;
estimated counts are allowed once cardinality exceeds it.
