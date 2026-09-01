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
            keys = self._keys(mapped)
            matches = [product for product in self.products if product.keys & keys]
            product = matches[0] if matches else Product()
            if not matches:
                self.products.append(product)
            for duplicate in matches[1:]:
                product.keys.update(duplicate.keys)
                product.source_ids.update(duplicate.source_ids)
                for field, version in duplicate.versions.items():
                    if version > product.versions.get(field, (-1, "")):
                        product.versions[field] = version
                        product.values[field] = duplicate.values[field]
                self.products.remove(duplicate)
            product.keys.update(keys)
            source_key = f"{row['source']}:{row['source_id']}"
            product.source_ids.add(source_key)
            version = (int(row["updated_at"]), row["source"])
            for field, value in mapped.items():
                if value and version >= product.versions.get(field, (-1, "")):
                    product.values[field] = value
                    product.versions[field] = version
        return self.snapshot()

    def _map(self, row: dict[str, Any]) -> dict[str, str]:
        return {
            target: str(row[source])
            for source, target in self.mappings[row["source"]].items()
            if row.get(source) not in (None, "")
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
