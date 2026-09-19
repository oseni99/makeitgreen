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


@pytest.mark.parametrize(
    ("source", "identity_fields", "tax_field", "tax_value"),
    [
        ("internal", {"sku": "A"}, "tax_code", "standard"),
        ("distributor", {"code": "A"}, "tax", "reduced"),
        ("spreadsheet", {"vendor_sku": "A"}, "tax_class", "zero"),
    ],
)
def test_tax_mapping_is_preserved_for_every_configured_source(
    source: str,
    identity_fields: dict,
    tax_field: str,
    tax_value: str,
) -> None:
    importer = CatalogImporter(MAPPINGS)
    result = importer.import_rows(
        [row(source, "source-1", 1, **identity_fields, **{tax_field: tax_value})]
    )
    assert result[0]["tax_code"] == tax_value


@pytest.mark.parametrize(
    ("first_sku", "second_sku"),
    [("sku-1", "SKU-1"), (" sku-1 ", "SKU-1"), ("Sku-1", "sKu-1")],
)
def test_normalized_sku_identity_merges_records_across_sources(
    first_sku: str,
    second_sku: str,
) -> None:
    importer = CatalogImporter(MAPPINGS)
    result = importer.import_rows(
        [
            row("internal", "i1", 1, sku=first_sku, description="First"),
            row("distributor", "d1", 2, code=second_sku, label="Second"),
        ]
    )
    assert len(result) == 1
    assert result[0]["source_ids"] == ["distributor:d1", "internal:i1"]


@pytest.mark.parametrize("stale_time", [0, 5, 9])
def test_each_older_arrival_preserves_newer_field_versions(stale_time: int) -> None:
    importer = CatalogImporter(MAPPINGS)
    importer.import_rows(
        [row("internal", "i1", 10, sku="A", description="Current")]
    )
    result = importer.import_rows(
        [row("distributor", "d1", stale_time, code="A", label="Stale")]
    )
    assert len(result) == 1
    assert result[0]["description"] == "Current"
