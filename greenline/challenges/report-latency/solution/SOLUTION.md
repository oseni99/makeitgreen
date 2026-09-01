# Solution — report-latency

## Root cause

`build_customer_report` did this:

1. Walk all orders to collect unique customer ids
2. **For each customer**, walk **all orders again** (`_orders_for_customer`)

That is Θ(customers · orders). The profiler dump makes it obvious:
`_orders_for_customer` / its listcomp dominate cumulative time with ~6k calls.
`json.dumps` at the end is a red herring (~0.4s, once).

## Fix

Group in a **single pass**, then aggregate each bucket:

```python
by_customer = defaultdict(list)
for order in orders:
    by_customer[order.customer_id].append(order)
```

One full iteration over `orders` (the test allows ≤ 3). Same answers, orders of
magnitude less work.

## Extra smell (optional cleanup)

`_unique_customer_ids` used `if id not in seen` on a **list**, which is Θ(n²) for
the uniqueness pass alone. A `set` (or the `defaultdict` approach above) removes
that too. The SLO burn was the nested scan, not this — but mention it in review.

## Interview talking points

- **Read the profiler before the code.** Hot frames + call counts beat guessing.
- Name the complexity: nested full scans are the classic “works in staging,
  dies in prod” report bug.
- Distinguish **once-per-job** cost (`json.dumps`) from **once-per-entity** cost
  (per-customer scan). Optimizing the wrong frame wastes the incident.
- When you lack a profiler in an interview, instrument with counters (the unit
  test’s `CountingSequence` is the same idea).
