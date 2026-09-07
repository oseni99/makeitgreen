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


def listed_entries() -> list[dict]:
    response = client.get("/entries")
    assert response.status_code == 200
    return response.json()["entries"]


def test_empty_ledger_returns_an_empty_collection() -> None:
    assert listed_entries() == []


def test_create_returns_entry_body() -> None:
    r = client.post("/entries", json=make_entry())
    body = r.json()
    assert body["account"] == "revenue"
    assert body["amount_cents"] == 4_200
    assert body["memo"] == "invoice #1"
    assert isinstance(body["id"], int)


def test_create_returns_201() -> None:
    r = client.post("/entries", json=make_entry())
    assert r.status_code == 201, f"POST /entries must return 201, got {r.status_code}"


def test_create_defaults_an_omitted_memo_to_empty_text() -> None:
    payload = {"account": "cash", "amount_cents": 500}

    response = client.post("/entries", json=payload)

    assert response.json()["memo"] == ""


def test_created_entries_receive_unique_increasing_ids() -> None:
    first = client.post("/entries", json=make_entry()).json()
    second = client.post("/entries", json=make_entry(memo="invoice #2")).json()

    assert second["id"] == first["id"] + 1


def test_list_entries() -> None:
    first = client.post("/entries", json=make_entry()).json()
    second = client.post("/entries", json=make_entry(memo="invoice #2")).json()

    assert listed_entries() == [first, second]


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


def test_missing_entry_returns_a_stable_error_body() -> None:
    response = client.get("/entries/999")

    assert response.headers.get("content-type") == "application/json"
    assert response.json() == {"detail": "entry not found"}


def test_non_integer_entry_id_is_rejected_as_invalid_input() -> None:
    response = client.get("/entries/not-an-integer")

    assert response.status_code == 422


@pytest.mark.parametrize("missing_field", ["account", "amount_cents"])
def test_required_create_fields_are_validated_without_writing(missing_field: str) -> None:
    payload = make_entry()
    payload.pop(missing_field)

    response = client.post("/entries", json=payload)

    assert response.status_code == 422
    assert listed_entries() == []


def test_idempotency_key_prevents_duplicates() -> None:
    """A client retry with the same Idempotency-Key must not double-record."""
    headers = {"Idempotency-Key": "retry-abc-123"}
    first = client.post("/entries", json=make_entry(), headers=headers)
    second = client.post("/entries", json=make_entry(), headers=headers)

    assert second.json()["id"] == first.json()["id"], "retry must return the original entry"
    entries = listed_entries()
    assert len(entries) == 1, f"expected 1 entry after retry, ledger has {len(entries)}"


def test_idempotent_retry_returns_the_complete_original_response() -> None:
    headers = {"Idempotency-Key": "retry-complete-response"}
    first = client.post("/entries", json=make_entry(), headers=headers)

    replay = client.post("/entries", json=make_entry(), headers=headers)

    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_idempotent_retry_still_finds_original_after_other_writes() -> None:
    headers = {"Idempotency-Key": "retry-after-other-write"}
    original = client.post("/entries", json=make_entry(), headers=headers).json()
    client.post("/entries", json=make_entry(account="fees", memo="processing fee"))

    replay = client.post("/entries", json=make_entry(), headers=headers)

    assert replay.json() == original
    assert len(listed_entries()) == 2


def test_different_idempotency_keys_create_independent_entries() -> None:
    first = client.post(
        "/entries",
        json=make_entry(),
        headers={"Idempotency-Key": "request-one"},
    ).json()
    second = client.post(
        "/entries",
        json=make_entry(),
        headers={"Idempotency-Key": "request-two"},
    ).json()

    assert first["id"] != second["id"]
    assert len(listed_entries()) == 2


def test_unkeyed_identical_requests_create_independent_entries() -> None:
    first = client.post("/entries", json=make_entry()).json()
    second = client.post("/entries", json=make_entry()).json()

    assert first["id"] != second["id"]
    assert len(listed_entries()) == 2


def test_reusing_key_for_different_payload_is_rejected_without_a_write() -> None:
    headers = {"Idempotency-Key": "payload-conflict"}
    original = client.post("/entries", json=make_entry(), headers=headers).json()

    conflict = client.post(
        "/entries",
        json=make_entry(amount_cents=9_900),
        headers=headers,
    )

    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "idempotency key already used for another request"}
    assert listed_entries() == [original]
