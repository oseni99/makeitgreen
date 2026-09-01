from __future__ import annotations

import hashlib

import pytest

from artifacts import ArtifactStore, SessionRepository


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def service(store: ArtifactStore | None = None, sessions: SessionRepository | None = None):
    try:
        from uploads import UploadService
    except ModuleNotFoundError:
        pytest.fail("create the uploads package and UploadService")
    return UploadService(store or ArtifactStore(), sessions or SessionRepository())


def test_chunks_may_arrive_out_of_order_and_survive_service_reconstruction() -> None:
    store, sessions = ArtifactStore(), SessionRepository()
    upload = service(store, sessions)
    data = b"hello world"
    session_id = upload.begin("result.txt", len(data), digest(data))
    upload.put_chunk(session_id, 2, b"world", digest(b"world"))
    upload = service(store, sessions)
    upload.put_chunk(session_id, 1, b"hello ", digest(b"hello "))
    assert upload.status(session_id) == {"received": [1, 2], "bytes_received": 11}
    artifact_id = upload.finalize(session_id, [1, 2])
    assert store.get(artifact_id) == data


def test_exact_chunk_retry_is_idempotent_but_conflict_preserves_original() -> None:
    from uploads import ChunkConflict, IntegrityError

    upload = service()
    session_id = upload.begin("x", 3, digest(b"abc"))
    upload.put_chunk(session_id, 1, b"abc", digest(b"abc"))
    upload.put_chunk(session_id, 1, b"abc", digest(b"abc"))
    with pytest.raises(ChunkConflict):
        upload.put_chunk(session_id, 1, b"abd", digest(b"abd"))
    with pytest.raises(IntegrityError):
        upload.put_chunk(session_id, 2, b"bad", "0" * 64)
    assert upload.status(session_id) == {"received": [1], "bytes_received": 3}


@pytest.mark.parametrize("order", [[1, 3], [1, 1, 2], [2, 1]])
def test_finalize_rejects_gaps_duplicates_and_noncanonical_order(order: list[int]) -> None:
    from uploads import IncompleteUpload

    upload = service()
    session_id = upload.begin("x", 3, digest(b"abc"))
    upload.put_chunk(session_id, 1, b"a", digest(b"a"))
    upload.put_chunk(session_id, 2, b"b", digest(b"b"))
    upload.put_chunk(session_id, 3, b"c", digest(b"c"))
    with pytest.raises(IncompleteUpload):
        upload.finalize(session_id, order)
    assert upload.status(session_id)["received"] == [1, 2, 3]


def test_failed_finalize_remains_correctable() -> None:
    from uploads import IntegrityError

    upload = service()
    session_id = upload.begin("x", 3, digest(b"abc"))
    upload.put_chunk(session_id, 1, b"ab", digest(b"ab"))
    with pytest.raises(IntegrityError, match="size"):
        upload.finalize(session_id, [1])
    upload.put_chunk(session_id, 2, b"c", digest(b"c"))
    assert upload.finalize(session_id, [1, 2]).startswith("sha256:")


def test_success_is_terminal_and_existing_content_is_deduplicated() -> None:
    from uploads import UploadClosed

    store = ArtifactStore()
    expected = store.put(b"abc")
    upload = service(store)
    session_id = upload.begin("duplicate", 3, digest(b"abc"))
    upload.put_chunk(session_id, 1, b"abc", digest(b"abc"))
    assert upload.finalize(session_id, [1]) == expected
    assert store.count == 1
    with pytest.raises(UploadClosed):
        upload.put_chunk(session_id, 2, b"x", digest(b"x"))
    with pytest.raises(UploadClosed):
        upload.finalize(session_id, [1])


def test_cancel_is_idempotent_and_removes_partial_data() -> None:
    from uploads import UploadNotFound

    upload = service()
    session_id = upload.begin("x", 3, digest(b"abc"))
    upload.put_chunk(session_id, 1, b"a", digest(b"a"))
    upload.cancel(session_id)
    upload.cancel(session_id)
    with pytest.raises(UploadNotFound):
        upload.status(session_id)


def test_empty_artifact_is_valid_and_input_is_validated() -> None:
    upload = service()
    with pytest.raises(ValueError):
        upload.begin("x", -1, digest(b""))
    session_id = upload.begin("empty", 0, digest(b""))
    artifact_id = upload.finalize(session_id, [])
    assert artifact_id == f"sha256:{digest(b'')}"
