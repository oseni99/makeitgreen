"""Ledger API handlers."""
from __future__ import annotations

from fastapi import FastAPI, Header, Request
from pydantic import BaseModel

from api.store import LedgerStore

app = FastAPI(title="ledger-api")
STORE = LedgerStore()


class EntryIn(BaseModel):
    account: str
    amount_cents: int
    memo: str = ""


@app.post("/entries")
def create_entry(
    body: EntryIn,
    idempotency_key: str | None = Header(default=None),
) -> dict:
    entry = STORE.add(body.account, body.amount_cents, body.memo)
    return entry


@app.get("/entries")
def list_entries() -> dict:
    return {"entries": STORE.list()}


@app.get("/entries/{entry_id}")
def get_entry(entry_id: int) -> dict:
    return STORE.entries[entry_id]
