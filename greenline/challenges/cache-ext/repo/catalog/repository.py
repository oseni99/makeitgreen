"""Working product repository; repeated reads currently reach storage."""
from __future__ import annotations

from catalog.models import Product


class ProductRepository:
    def __init__(self) -> None:
        self._products: dict[str, Product] = {}
        self.storage_reads = 0

    def save(self, product: Product) -> None:
        if not product.sku or not product.name:
            raise ValueError("sku and name are required")
        if product.price_cents < 0:
            raise ValueError("price cannot be negative")
        self._products[product.sku] = product

    def get(self, sku: str) -> Product | None:
        self.storage_reads += 1
        return self._products.get(sku)

    def delete(self, sku: str) -> bool:
        return self._products.pop(sku, None) is not None

    def list_all(self) -> list[Product]:
        return [self._products[sku] for sku in sorted(self._products)]
