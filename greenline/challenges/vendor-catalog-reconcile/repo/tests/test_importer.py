import json
from pathlib import Path

import pytest

from catalog import CatalogImporter, UnidentifiableRow

MAPPINGS = json.loads((Path(__file__).parents[1] / "fixtures/mappings.json").read_text())


def row(source: str, source_id: str, updated_at: int, **fields):
    return {"source": source, "source_id": source_id, "updated_at": updated_at, **fields}


def test_configured_fields_include_tax_code() -> None:
    importer = CatalogImporter(MAPPINGS)
    result = importer.import_rows([
        row("distributor", "d1", 1, code="sku-1", barcode="111", label="Cable", tax="standard")
    ])
    assert result[0]["tax_code"] == "standard"


def test_same_gtin_merges_sources_and_preserves_newest_fields() -> None:
    importer = CatalogImporter(MAPPINGS)
    result = importer.import_rows([
        row("distributor", "d1", 10, code="old", barcode="111", label="Old cable", tax="standard"),
        row("spreadsheet", "s1", 20, vendor_sku="new", gtin13="111", name="New cable", tax_class="reduced"),
    ])
    assert len(result) == 1
    assert result[0]["description"] == "New cable"
    assert result[0]["source_ids"] == ["distributor:d1", "spreadsheet:s1"]


def test_stale_late_row_does_not_overwrite_newer_values() -> None:
    importer = CatalogImporter(MAPPINGS)
    importer.import_rows([
        row("internal", "i1", 20, sku="A-1", gtin="111", description="Current", tax_code="standard")
    ])
    result = importer.import_rows([
        row("distributor", "d1", 5, code="A-1", barcode="111", label="Stale", tax="reduced")
    ])
    assert result[0]["description"] == "Current"
    assert result[0]["tax_code"] == "standard"


def test_bridge_row_merges_two_previously_separate_products() -> None:
    importer = CatalogImporter(MAPPINGS)
    importer.import_rows([
        row("internal", "i1", 1, sku="SKU-1", description="Internal"),
        row("distributor", "d1", 1, code="OTHER", barcode="111", label="Vendor"),
    ])
    result = importer.import_rows([
        row("spreadsheet", "s1", 2, vendor_sku="SKU-1", gtin13="111", name="Unified")
    ])
    assert len(result) == 1
    assert result[0]["source_ids"] == ["distributor:d1", "internal:i1", "spreadsheet:s1"]


def test_replay_is_idempotent_and_stably_ordered() -> None:
    importer = CatalogImporter(MAPPINGS)
    rows = [
        row("internal", "z", 1, sku="Z", description="Zulu"),
        row("internal", "a", 1, sku="A", description="Alpha"),
    ]
    first = importer.import_rows(rows)
    second = importer.import_rows(rows)
    assert second == first
    assert [item["description"] for item in second] == ["Alpha", "Zulu"]


def test_only_truly_unidentifiable_rows_are_rejected() -> None:
    importer = CatalogImporter(MAPPINGS)
    with pytest.raises(UnidentifiableRow):
        importer.import_rows([row("internal", "i1", 1, description="No identity")])
