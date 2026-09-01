from artifacts import ArtifactStore


def test_store_is_content_addressed_and_deduplicates() -> None:
    store = ArtifactStore()
    first = store.put(b"build output")
    second = store.put(b"build output")
    assert first == second
    assert first.startswith("sha256:")
    assert store.get(first) == b"build output"
    assert store.count == 1
