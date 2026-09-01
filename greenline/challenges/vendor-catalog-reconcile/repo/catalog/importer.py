from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class UnidentifiableRow(ValueError):
    pass


@dataclass
class Product:
    keys: set[str] = field(default_factory=set)
    source_ids: set[str] = field(default_factory=set)
    values: dict[str, str] = field(default_factory=dict)
    versions: dict[str, tuple[int, str]] = field(default_factory=dict)


class CatalogImporter:
    def __init__(self, mappings: dict[str, dict[str, str]]) -> None:
        self.mappings = mappings
        self.products: list[Product] = []

    def import_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for row in rows:
            mapped = self._map(row)
            source_key = f"{row['source']}:{row['source_id']}"
            # BUG: source record identity is mistaken for product identity.
            product = next((p for p in self.products if source_key in p.source_ids), None)
            if product is None:
                product = Product()
                self.products.append(product)
            product.source_ids = {source_key}
            product.keys.update(self._keys(mapped))
            # BUG: arrival order wins even when the row is older.
            product.values.update({key: value for key, value in mapped.items() if value})
        return self.snapshot()

    def _map(self, row: dict[str, Any]) -> dict[str, str]:
        mapping = self.mappings[row["source"]]
        # BUG: tax_code is silently omitted from the configured mapping.
        return {
            target: str(row[source])
            for source, target in mapping.items()
            if target != "tax_code" and row.get(source) not in (None, "")
        }

    @staticmethod
    def _keys(mapped: dict[str, str]) -> set[str]:
        keys = set()
        if mapped.get("gtin"):
            keys.add(f"gtin:{mapped['gtin']}")
        if mapped.get("sku"):
            keys.add(f"sku:{mapped['sku'].strip().upper()}")
        if not keys:
            raise UnidentifiableRow("row has no GTIN or SKU")
        return keys

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {**product.values, "source_ids": sorted(product.source_ids)}
            for product in sorted(self.products, key=lambda item: sorted(item.keys)[0])
        ]
