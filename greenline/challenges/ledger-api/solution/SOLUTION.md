# Solution — ledger-api

## Bug 1 — POST returns 200 instead of 201

FastAPI defaults every route to 200. A resource-creating endpoint must
declare its status:

```python
@app.post("/entries", status_code=201)
```

Trivial fix, but it's the exact kind of contract drift PR reviews exist to
catch — clients keying on `if resp.status == 201` silently break.

## Bug 2 — 500 on missing entry

`STORE.entries[entry_id]` raises `KeyError`, which surfaces as a 500.
Clients can't distinguish "you asked for something that doesn't exist"
(their bug) from "the server crashed" (our bug) — and 500s typically trigger
client retries, making it worse.

```python
if entry_id not in STORE.entries:
    raise HTTPException(status_code=404, detail="entry not found")
```

## Bug 3 — Idempotency-Key ignored

The handler accepted the header and did nothing with it. Every retry
recorded a new ledger entry — double-charging on flaky networks.

Fix: keep a key → entry-id map in the store. The lookup, payload comparison,
write, and key registration must happen under one lock so simultaneous callers
cannot both observe a missing key:

```python
with self._lock:
    existing_id = self.idempotency.get(idempotency_key)
    if existing_id is not None:
        # Compare the stored request fields, then replay or raise a conflict.
        return self.entries[existing_id]
    entry = self._add_unlocked(...)
    self.idempotency[idempotency_key] = entry["id"]
    return entry
```

The key represents one logical request, not a reusable cache key. Before
replaying the stored entry, compare the incoming account, amount, and memo to
the original request. If they differ, return `409 Conflict` and make no write.
That prevents a caller from accidentally receiving a successful response for
different ledger data.

## Interview talking points

- This is the "what happens if the request is sent twice?" question in code
  form — the single most common API-design follow-up.
- Production-grade idempotency stores a request fingerprint explicitly and
  expires keys according to a documented retention policy. This exercise uses
  the stored entry fields as its fingerprint because the request maps directly
  to one entry.
- Replay status code: APIs can choose 200 or 201, but the contract must be
  consistent. This exercise returns 201 for both the original POST and replay.
- 404 vs 500 isn't cosmetic: 5xx usually means "retry me", 4xx means "your
  fault, stop". Wrong class = retry storms.

## Supporting contract repairs

The request model keeps `account` and `amount_cents` required and gives `memo`
an empty-string default. The list handler returns a collection in insertion
order even when empty. Typing the route parameter as `int` lets FastAPI return
422 for malformed IDs, while an explicit `HTTPException` provides the stable
JSON 404 response for an unknown integer ID.
