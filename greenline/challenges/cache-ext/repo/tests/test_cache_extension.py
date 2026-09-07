from __future__ import annotations

import pytest

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


@pytest.mark.parametrize("ttl", [0.1, 1, 10])
def test_ttl_cache_expires_at_boundary_without_sleeping(ttl: float) -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=ttl, clock=clock)
    cache.set("sku", "value")

    assert cache.get("sku") == "value"
    clock.advance(ttl - 0.001)
    assert cache.get("sku") == "value"
    clock.advance(0.001)
    assert cache.get("sku") is None


@pytest.mark.parametrize("read_count", [2, 5])
def test_repeated_repository_read_hits_storage_once_before_expiry(
    read_count: int,
) -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=10, clock=clock)
    repo = ProductRepository(cache=cache)
    product = Product("sku", "Cached", 100)
    repo.save(product)

    for _ in range(read_count):
        assert repo.get("sku") == product
    assert repo.storage_reads == 1


@pytest.mark.parametrize("ttl", [1, 5])
def test_expired_entry_is_refreshed_from_storage(ttl: float) -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=ttl, clock=clock)
    repo = ProductRepository(cache=cache)
    repo.save(Product("sku", "Cached", 100))

    repo.get("sku")
    clock.advance(ttl)
    assert repo.get("sku") == Product("sku", "Cached", 100)
    assert repo.storage_reads == 2


@pytest.mark.parametrize("new_price", [125, 999])
def test_save_invalidates_cached_product(new_price: int) -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=60, clock=clock)
    repo = ProductRepository(cache=cache)
    repo.save(Product("sku", "Old", 100))
    assert repo.get("sku").name == "Old"

    repo.save(Product("sku", "New", new_price))

    assert repo.get("sku") == Product("sku", "New", new_price)
    assert repo.storage_reads == 2


@pytest.mark.parametrize("deleted_sku", ["a", "b", "c"])
def test_delete_invalidates_cached_product_without_touching_other_keys(
    deleted_sku: str,
) -> None:
    clock = FakeClock()
    cache = _cache_cls()(ttl_seconds=60, clock=clock)
    repo = ProductRepository(cache=cache)
    repo.save(Product("a", "A", 100))
    repo.save(Product("b", "B", 200))
    repo.save(Product("c", "C", 300))
    assert repo.get("a") is not None
    assert repo.get("b") is not None

    assert repo.get("c") is not None
    assert repo.delete(deleted_sku) is True

    expected = {"a": Product("a", "A", 100), "b": Product("b", "B", 200), "c": Product("c", "C", 300)}
    assert repo.get(deleted_sku) is None
    for sku, product in expected.items():
        if sku != deleted_sku:
            assert repo.get(sku) == product
    assert repo.storage_reads == 4
