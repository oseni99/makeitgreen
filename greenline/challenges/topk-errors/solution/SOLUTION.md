# Solution — bounded heavy hitters

## Root cause

The starter keeps an exact counter for every distinct service identifier. That is
exact, but memory grows with untrusted tag cardinality and matches the retained-heap
evidence.

## Fix

The solution uses the Space-Saving algorithm. Existing counters increment normally.
While space remains, a new service receives a counter of one. At capacity, the
smallest counter is replaced and the new service receives `minimum + 1`. State is
therefore always bounded by `capacity`, while frequent services remain candidates.

## Interview talking points

- Exact top-K for a non-replayable, unbounded-cardinality stream requires unbounded
  state; approximation is a product decision, not an implementation accident.
- Space-Saving estimates can overcount. A production API should expose approximation
  semantics and possibly an error bound.
- Deterministic tie-breaking makes tests and operational output stable.
- Real telemetry systems must also control cardinality before aggregation and defend
  against adversarial identifiers.
