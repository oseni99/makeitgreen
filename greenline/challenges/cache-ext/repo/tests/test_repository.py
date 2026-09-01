from __future__ import annotations

import pytest

from catalog.models import Product
from catalog.repository import ProductRepository


def test_existing_repository_crud_behavior() -> None:
    repo = ProductRepository()
    first = Product("sku-b", "Beta", 200)
    second = Product("sku-a", "Alpha", 100)
    repo.save(first)
    repo.save(second)

    assert repo.get("sku-b") == first
    assert repo.list_all() == [second, first]
    assert repo.delete("sku-b") is True
    assert repo.delete("sku-b") is False
    assert repo.get("sku-b") is None


def test_existing_validation_stays_green() -> None:
    repo = ProductRepository()
    with pytest.raises(ValueError, match="required"):
        repo.save(Product("", "Missing SKU", 100))
    with pytest.raises(ValueError, match="negative"):
        repo.save(Product("sku", "Bad price", -1))


def test_repository_without_cache_reads_storage_each_time() -> None:
    repo = ProductRepository()
    repo.save(Product("sku", "Plain", 100))
    repo.get("sku")
    repo.get("sku")
    assert repo.storage_reads == 2
