# ledger-api

A minimal double-entry-ish ledger REST API (FastAPI).

- `api/app.py` — HTTP handlers
- `api/store.py` — in-memory persistence

Contract:
- `POST /entries` — record an entry → **201** with the entry body.
  `account` and `amount_cents` are required; omitted `memo` defaults to `""`.
  Invalid bodies return **422** without writing, and successful entries receive
  unique increasing integer IDs.
  Supports an optional `Idempotency-Key` header: retries with the same key
  and the same request must return the original entry without creating a
  second one, including under concurrent requests. A replay returns **201**.
  Reusing a key with a different request must return **409** and leave the
  ledger unchanged. Different keys and requests without keys are independent.
- `GET /entries` — return `{"entries": [...]}` → **200**. The list is empty
  for a new ledger and preserves entry creation order.
- `GET /entries/{id}` — fetch one entry → **200**. An unknown integer ID
  returns **404** with `{"detail": "entry not found"}`; a malformed ID returns
  **422**.

Run tests: `python -m pytest -v`
