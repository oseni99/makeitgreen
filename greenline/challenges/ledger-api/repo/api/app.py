"""Ledger API handlers."""
from __future__ import annotations

from fastapi import FastAPI, Header, Request
from pydantic import BaseModel

from api.store import LedgerStore

app = FastAPI(title="ledger-api")
STORE = LedgerStore()


class EntryIn(BaseModel):
    # A rushed compatibility change made every field optional and changed the
    # memo default. The API now accepts requests the contract rejects.
    account: str | None = None
    amount_cents: int | None = None
    memo: str | None = None


@app.post("/entries")
def create_entry(
    body: EntryIn,
    idempotency_key: str | None = Header(default=None),
) -> dict:
    entry = STORE.add(body.account, body.amount_cents, body.memo)
    return entry


@app.get("/entries")
def list_entries() -> dict:
    entries = STORE.list()
    # The mobile adapter expects a collection even when it is empty and keeps
    # the ledger's insertion order.
    return {"entries": list(reversed(entries)) if entries else None}


@app.get("/entries/{entry_id}")
def get_entry(entry_id: str) -> dict:
    # Manual conversion turns malformed IDs and missing records into 500s.
    return STORE.entries[int(entry_id)]
