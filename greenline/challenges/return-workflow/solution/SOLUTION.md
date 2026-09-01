# Solution — return-workflow

The broken implementation validated only that the target was a known state. That made
the state names look controlled while still allowing skips, reversals, cancellation
after warehouse receipt, and movement out of terminal states.

## Fix

Define one transition table keyed by the current state:

```python
ALLOWED_TRANSITIONS = {
    "requested": {"authorized", "cancelled"},
    "authorized": {"received", "cancelled"},
    "received": {"inspected"},
    "inspected": {"refunded", "rejected"},
    "refunded": set(),
    "rejected": set(),
    "cancelled": set(),
}
```

`transition()` checks the pair before changing either the current state or history.
That ordering makes a rejected operation an atomic no-op. Terminal behavior is visible
in the same table rather than being scattered through special cases.

## Interview talking points

- Valid state names and valid state transitions are different invariants.
- A transition and its audit record belong to one logical mutation.
- Terminal states are easiest to audit when they appear explicitly with no outgoing
  edges.
- The transition table makes future lifecycle changes reviewable and testable.
