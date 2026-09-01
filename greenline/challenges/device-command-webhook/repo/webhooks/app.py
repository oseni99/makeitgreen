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


@app.post("/webhooks/batch")
def receive(batch: Batch) -> dict:
    applied = 0
    statuses: list[str] = []
    for event in batch.events:
        fingerprint = (event.device_id, event.sequence, event.state)
        if event.delivery_id in store.deliveries:
            statuses.append("duplicate")
            continue
        # BUG: every unseen event is applied immediately, even across a gap or
        # behind the already-applied sequence.
        store.device_state[event.device_id] = event.state
        store.last_sequence[event.device_id] = max(
            event.sequence, store.last_sequence.get(event.device_id, 0)
        )
        store.deliveries[event.delivery_id] = fingerprint
        store.effects.append(fingerprint)
        applied += 1
        statuses.append("applied")
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
