import pytest
from fastapi.testclient import TestClient

from api.app import STORE, app

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_store():
    STORE.clear()
    yield


def make_entry(**overrides):
    payload = {"account": "revenue", "amount_cents": 4_200, "memo": "invoice #1"}
    payload.update(overrides)
    return payload


def test_create_returns_entry_body() -> None:
    r = client.post("/entries", json=make_entry())
    body = r.json()
    assert body["account"] == "revenue"
    assert body["amount_cents"] == 4_200
    assert isinstance(body["id"], int)


def test_create_returns_201() -> None:
    r = client.post("/entries", json=make_entry())
    assert r.status_code == 201, f"POST /entries must return 201, got {r.status_code}"


def test_list_entries() -> None:
    client.post("/entries", json=make_entry())
    client.post("/entries", json=make_entry(memo="invoice #2"))
    r = client.get("/entries")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 2


def test_get_existing_entry() -> None:
    created = client.post("/entries", json=make_entry()).json()
    r = client.get(f"/entries/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_missing_entry_returns_404() -> None:
    r = client.get("/entries/999")
    assert r.status_code == 404, (
        f"unknown entry must return 404, got {r.status_code} — "
        "clients cannot tell 'not found' from 'server on fire'"
    )


def test_idempotency_key_prevents_duplicates() -> None:
    """A client retry with the same Idempotency-Key must not double-record."""
    headers = {"Idempotency-Key": "retry-abc-123"}
    first = client.post("/entries", json=make_entry(), headers=headers)
    second = client.post("/entries", json=make_entry(), headers=headers)

    assert second.json()["id"] == first.json()["id"], "retry must return the original entry"
    entries = client.get("/entries").json()["entries"]
    assert len(entries) == 1, f"expected 1 entry after retry, ledger has {len(entries)}"
