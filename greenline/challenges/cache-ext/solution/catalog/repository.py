"""Product repository with an optional cache collaborator."""
from __future__ import annotations

from typing import Protocol

from catalog.models import Product


class ProductCache(Protocol):
    def get(self, key: str) -> Product | None: ...
    def set(self, key: str, value: Product) -> None: ...
    def delete(self, key: str) -> None: ...


class ProductRepository:
    def __init__(self, cache: ProductCache | None = None) -> None:
        self._products: dict[str, Product] = {}
        self._cache = cache
        self.storage_reads = 0

    def save(self, product: Product) -> None:
        if not product.sku or not product.name:
            raise ValueError("sku and name are required")
        if product.price_cents < 0:
            raise ValueError("price cannot be negative")
        self._products[product.sku] = product
        if self._cache is not None:
            self._cache.delete(product.sku)

    def get(self, sku: str) -> Product | None:
        if self._cache is not None:
            cached = self._cache.get(sku)
            if cached is not None:
                return cached

        self.storage_reads += 1
        product = self._products.get(sku)
        if product is not None and self._cache is not None:
            self._cache.set(sku, product)
        return product

    def delete(self, sku: str) -> bool:
        removed = self._products.pop(sku, None) is not None
        if self._cache is not None:
            self._cache.delete(sku)
        return removed

    def list_all(self) -> list[Product]:
        return [self._products[sku] for sku in sorted(self._products)]
