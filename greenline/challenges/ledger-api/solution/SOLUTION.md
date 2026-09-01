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

Fix: keep a key → entry-id map in the store; on a known key, return the
original entry instead of writing:

```python
if idempotency_key and (eid := STORE.idempotency.get(idempotency_key)):
    return STORE.entries[eid]
entry = STORE.add(...)
if idempotency_key:
    STORE.idempotency[idempotency_key] = entry["id"]
```

## Interview talking points

- This is the "what happens if the request is sent twice?" question in code
  form — the single most common API-design follow-up.
- Production-grade idempotency also stores a *fingerprint* of the request and
  rejects a reused key with a different body (409), and expires keys (e.g.
  Stripe: 24h). Mentioning either is strong signal.
- Replay status code: returning 201 on the replay (what Stripe does) vs 200 —
  either is defensible if it's consistent; the test here accepts both.
- 404 vs 500 isn't cosmetic: 5xx usually means "retry me", 4xx means "your
  fault, stop". Wrong class = retry storms.
