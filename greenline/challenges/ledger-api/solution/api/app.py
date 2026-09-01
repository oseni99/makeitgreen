"""Ledger API handlers."""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from api.store import LedgerStore

app = FastAPI(title="ledger-api")
STORE = LedgerStore()


class EntryIn(BaseModel):
    account: str
    amount_cents: int
    memo: str = ""


@app.post("/entries", status_code=201)
def create_entry(
    body: EntryIn,
    idempotency_key: str | None = Header(default=None),
) -> dict:
    if idempotency_key is not None:
        existing_id = STORE.idempotency.get(idempotency_key)
        if existing_id is not None:
            return STORE.entries[existing_id]

    entry = STORE.add(body.account, body.amount_cents, body.memo)
    if idempotency_key is not None:
        STORE.idempotency[idempotency_key] = entry["id"]
    return entry


@app.get("/entries")
def list_entries() -> dict:
    return {"entries": STORE.list()}


@app.get("/entries/{entry_id}")
def get_entry(entry_id: int) -> dict:
    if entry_id not in STORE.entries:
        raise HTTPException(status_code=404, detail="entry not found")
    return STORE.entries[entry_id]
