# Solution — transfer-deadlock

## Root cause

`TransferService.transfer()` acquires locks in **transfer direction** (`src` then `dst`).
When two threads move money in opposite directions concurrently:

- Thread 1 locks **alice**, waits for **bob**
- Thread 2 locks **bob**, waits for **alice**

Neither can proceed — a classic **deadlock** (circular wait).

## Fix

Acquire locks in a **global order** independent of transfer direction. Sorting
account IDs lexicographically is the standard bank-transfer pattern:

```python
first, second = (src, dst) if src < dst else (dst, src)
with self._store.lock(first):
    with self._store.lock(second):
        ...
```

Both threads now lock `alice` before `bob`, so one waits briefly instead of
deadlocking forever.

## Interview talking points

- Name the four Coffman conditions; here you break **circular wait** via lock ordering.
- Alternative: a single global transfer lock (simple, serializes everything) vs
  ordered per-account locks (parallel disjoint transfers still run concurrently).
- In production this state lives in a database: `SELECT ... FOR UPDATE` in primary-key
  order achieves the same invariant.
- `threading.Lock` is not reentrant — don't lock the same account twice on one thread
  without `RLock` (not an issue here because `src != dst`).
