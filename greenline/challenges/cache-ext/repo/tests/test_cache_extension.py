from __future__ import annotations

from catalog.models import Product
from catalog.repository import ProductRepository


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _cache_cls():
    # Keep a missing extension as an ordinary failed test, not collection error.
    from cache.ttl import TTLCache

    return TTLCache


def test_ttl_cache_expires_at_boundary_without_sleeping() -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=10, clock=clock)
    cache.set("sku", "value")

    assert cache.get("sku") == "value"
    clock.advance(9.999)
    assert cache.get("sku") == "value"
    clock.advance(0.001)
    assert cache.get("sku") is None


def test_repeated_repository_read_hits_storage_once_before_expiry() -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=10, clock=clock)
    repo = ProductRepository(cache=cache)
    product = Product("sku", "Cached", 100)
    repo.save(product)

    assert repo.get("sku") == product
    assert repo.get("sku") == product
    assert repo.storage_reads == 1


def test_expired_entry_is_refreshed_from_storage() -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=5, clock=clock)
    repo = ProductRepository(cache=cache)
    repo.save(Product("sku", "Cached", 100))

    repo.get("sku")
    clock.advance(5)
    assert repo.get("sku") == Product("sku", "Cached", 100)
    assert repo.storage_reads == 2


def test_save_invalidates_cached_product() -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=60, clock=clock)
    repo = ProductRepository(cache=cache)
    repo.save(Product("sku", "Old", 100))
    assert repo.get("sku").name == "Old"

    repo.save(Product("sku", "New", 125))

    assert repo.get("sku") == Product("sku", "New", 125)
    assert repo.storage_reads == 2


def test_delete_invalidates_cached_product_without_touching_other_keys() -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=60, clock=clock)
    repo = ProductRepository(cache=cache)
    repo.save(Product("a", "A", 100))
    repo.save(Product("b", "B", 200))
    assert repo.get("a") is not None
    assert repo.get("b") is not None

    assert repo.delete("a") is True

    assert repo.get("a") is None
    assert repo.get("b") == Product("b", "B", 200)
    assert repo.storage_reads == 3
