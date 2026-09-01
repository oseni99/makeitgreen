from __future__ import annotations

from copy import deepcopy
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class Event(BaseModel):
    delivery_id: str
    device_id: str
    sequence: int
    state: Literal["queued", "running", "succeeded", "failed"]


class Batch(BaseModel):
    events: list[Event]


class Store:
    def __init__(self) -> None:
        self.last_sequence: dict[str, int] = {}
        self.device_state: dict[str, str] = {}
        self.deliveries: dict[str, tuple[str, int, str]] = {}
        self.pending: dict[str, dict[int, Event]] = {}
        self.effects: list[tuple[str, int, str]] = []


store = Store()
app = FastAPI()


def reset_state() -> None:
    global store
    store = Store()


def _apply(target: Store, event: Event) -> None:
    target.device_state[event.device_id] = event.state
    target.last_sequence[event.device_id] = event.sequence
    target.effects.append((event.device_id, event.sequence, event.state))


@app.post("/webhooks/batch")
def receive(batch: Batch) -> dict:
    global store
    working = deepcopy(store)
    applied = 0
    statuses: list[str] = []
    try:
        for event in batch.events:
            fingerprint = (event.device_id, event.sequence, event.state)
            prior = working.deliveries.get(event.delivery_id)
            if prior is not None:
                if prior != fingerprint:
                    raise HTTPException(409, "delivery ID reused with different payload")
                statuses.append("duplicate")
                continue
            working.deliveries[event.delivery_id] = fingerprint
            last = working.last_sequence.get(event.device_id, 0)
            if event.sequence <= last:
                statuses.append("stale")
                continue
            if event.sequence > last + 1:
                working.pending.setdefault(event.device_id, {})[event.sequence] = event
                statuses.append("deferred")
                continue
            _apply(working, event)
            applied += 1
            statuses.append("applied")
            pending = working.pending.setdefault(event.device_id, {})
            while working.last_sequence[event.device_id] + 1 in pending:
                next_event = pending.pop(working.last_sequence[event.device_id] + 1)
                _apply(working, next_event)
                applied += 1
    except HTTPException:
        raise
    store = working
    return {"statuses": statuses, "applied_count": applied}


@app.get("/devices/{device_id}")
def device(device_id: str) -> dict:
    if device_id not in store.device_state:
        raise HTTPException(404, "device has no applied result")
    return {
        "device_id": device_id,
        "sequence": store.last_sequence[device_id],
        "state": store.device_state[device_id],
        "effects": [item for item in store.effects if item[0] == device_id],
    }
