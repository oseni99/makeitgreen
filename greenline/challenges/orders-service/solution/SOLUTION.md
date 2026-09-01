# Solution — orders-service

## Root cause

`Inventory.reserve()` is a **check-then-act race**. The availability check and
the decrement are separate steps with I/O in between (the simulated
fraud/payment round-trip). Under concurrency, many threads pass the check
while stock is still available, then *all* of them decrement — driving stock
negative.

This is the classic TOCTOU (time-of-check to time-of-use) bug. The `sleep`
only widens the window; the race exists without it.

## Fix

Make check + decrement atomic with a lock. A single global lock works but
serializes *all* SKUs; a lock **per SKU** keeps unrelated checkouts parallel —
which is what the brief asked to preserve.

```python
def reserve(self, sku: str, qty: int) -> None:
    lock = self._locks[sku]          # per-SKU lock via defaultdict
    with lock:
        if self._stock.get(sku, 0) < qty:
            raise InsufficientStock(sku)
        time.sleep(0.001)
        self._stock[sku] -= qty
```

Note `defaultdict(threading.Lock)` itself has a subtle thread-safety caveat:
two threads can race creating the lock for a brand-new SKU. Guarding lock
creation with a small meta-lock (as in the reference file) closes it.

## Interview talking points

- Name the bug class out loud: "check-then-act race / TOCTOU."
- Trade-off: global lock (simple, serializes everything) vs per-key lock
  (parallel, more code) vs optimistic CAS/atomics (no locks, retry loop).
- In a real service this state lives in a database: the equivalent fixes are
  `SELECT ... FOR UPDATE`, an atomic `UPDATE ... WHERE stock >= qty`, or a
  unique reservation ledger. Interviewers love hearing the DB mapping.
- Holding the lock across the simulated I/O is defensible here (correctness
  first) but worth flagging: in production you'd authorize payment *before*
  or *after* the critical section, not inside it.
