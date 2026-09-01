# ledger-api

A minimal double-entry-ish ledger REST API (FastAPI).

- `api/app.py` — HTTP handlers
- `api/store.py` — in-memory persistence

Contract:
- `POST /entries` — record an entry → **201** with the entry body.
  Supports an optional `Idempotency-Key` header: retries with the same key
  must not create a second entry.
- `GET /entries` — list all entries → 200
- `GET /entries/{id}` — fetch one entry → 200, or **404** if unknown

Run tests: `python -m pytest -v`
