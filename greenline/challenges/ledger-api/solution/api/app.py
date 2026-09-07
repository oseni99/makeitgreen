"""Ledger API handlers."""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from api.store import IdempotencyConflict, LedgerStore

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
    try:
        return STORE.create(
            body.account,
            body.amount_cents,
            body.memo,
            idempotency_key,
        )
    except IdempotencyConflict:
        raise HTTPException(
            status_code=409,
            detail="idempotency key already used for another request",
        ) from None


@app.get("/entries")
def list_entries() -> dict:
    return {"entries": STORE.list()}


@app.get("/entries/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = STORE.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry
