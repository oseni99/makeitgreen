# Solution

## Root cause

The endpoint rendered every historical event into a large dictionary before sorting and slicing. The response was bounded, but its most expensive allocation was not.

## Repair

Use a bounded top-K selection over the one-pass iterable, then render only the selected events in final order. A zero limit returns before consuming the cursor.

## Interview talking points

- `heapq.nlargest` bounds selection state to O(K), while full sorting uses O(N) references and O(N log N) work.
- The strongest production fix is pushing stable keyset ordering and limit into the database; this repair protects the service boundary when only an iterable is available.
- A deterministic secondary key prevents pagination and test instability for equal timestamps.
