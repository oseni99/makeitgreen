"""Online-write and backfill contract for the cents migration."""
from __future__ import annotations

from pathlib import Path

import pytest

from billing.service import InvoiceDatabase, MigrationRunner


@pytest.fixture
def database(tmp_path: Path) -> InvoiceDatabase:
    return InvoiceDatabase(str(tmp_path / "invoices.db"))


def test_new_invoice_is_dual_written_with_exact_cents(database: InvoiceDatabase) -> None:
    database.create_invoice(10, "12.35", "2.25")
    row = database.invoice(10)
    assert row["amount"] == "12.35"
    assert (row["subtotal_cents"], row["tax_cents"], row["total_cents"]) == (
        1010,
        225,
        1235,
    )


def test_decimal_conversion_does_not_use_binary_float(database: InvoiceDatabase) -> None:
    database.create_invoice(11, "10.10", "0.10")
    row = database.invoice(11)
    assert row["subtotal_cents"] + row["tax_cents"] == row["total_cents"] == 1010


def test_sparse_legacy_ids_are_processed_in_bounded_keyset_batches(
    database: InvoiceDatabase,
) -> None:
    for invoice_id in (2, 10, 50, 90, 120):
        database.seed_legacy(invoice_id, "5.00", "0.75")
    runner = MigrationRunner(database)

    assert runner.run_batch(2) == 2
    assert database.unmigrated_ids() == [50, 90, 120]
    assert runner.run_batch(2) == 2
    assert database.unmigrated_ids() == [120]
    assert runner.run_batch(2) == 1
    assert database.unmigrated_ids() == []
    assert database.state()["completed"] is True


def test_invoice_inserted_between_batches_is_not_skipped(database: InvoiceDatabase) -> None:
    database.seed_legacy(10, "8.00", "1.00")
    database.seed_legacy(30, "9.00", "1.00")
    runner = MigrationRunner(database)
    assert runner.run_batch(1) == 1

    # Simulates an older application instance still writing the legacy shape.
    database.seed_legacy(20, "7.00", "1.00")
    assert runner.run_batch(1) == 1
    assert runner.run_batch(1) == 1
    assert database.unmigrated_ids() == []


def test_failed_batch_rolls_back_rows_and_checkpoint(database: InvoiceDatabase) -> None:
    database.seed_legacy(1, "4.00", "0.50")
    database.seed_legacy(2, "6.00", "1.00")
    runner = MigrationRunner(database)

    def fail() -> None:
        raise RuntimeError("worker terminated")

    with pytest.raises(RuntimeError, match="terminated"):
        runner.run_batch(2, before_commit=fail)

    assert database.unmigrated_ids() == [1, 2]
    assert database.state() == {"last_id": 0, "completed": False}


def test_stale_completed_checkpoint_cannot_hide_unmigrated_rows(
    database: InvoiceDatabase,
) -> None:
    database.seed_legacy(5, "3.00", "0.25")
    database.force_state(last_id=999, completed=True)
    runner = MigrationRunner(database)

    assert runner.run_batch(10) == 1
    assert database.unmigrated_ids() == []
    assert database.state()["completed"] is True


def test_rerunning_completed_migration_is_safe_no_op(database: InvoiceDatabase) -> None:
    database.seed_legacy(7, "2.00", "0.20")
    runner = MigrationRunner(database)
    assert runner.run_batch(10) == 1
    first = database.invoice(7)
    assert runner.run_batch(10) == 0
    assert database.invoice(7) == first


@pytest.mark.parametrize(
    ("amount", "tax", "expected"),
    [
        ("0.00", "0.00", (0, 0, 0)),
        ("1.00", "0.00", (100, 0, 100)),
        ("1.01", "0.01", (100, 1, 101)),
        ("19.99", "1.25", (1874, 125, 1999)),
        ("1000000.00", "200000.00", (80000000, 20000000, 100000000)),
    ],
)
def test_live_writes_preserve_exact_cents_for_boundary_amounts(
    database: InvoiceDatabase,
    amount: str,
    tax: str,
    expected: tuple[int, int, int],
) -> None:
    database.create_invoice(99, amount, tax)
    row = database.invoice(99)
    assert (row["subtotal_cents"], row["tax_cents"], row["total_cents"]) == expected


@pytest.mark.parametrize("batch_size", [0, -1])
def test_batch_size_must_be_positive(
    database: InvoiceDatabase,
    batch_size: int,
) -> None:
    with pytest.raises(ValueError, match="positive"):
        MigrationRunner(database).run_batch(batch_size)


def test_backfill_uses_decimal_rounding_for_fractional_cents(
    database: InvoiceDatabase,
) -> None:
    database.seed_legacy(1, "1.005", "0.005")

    assert MigrationRunner(database).run_batch(1) == 1
    row = database.invoice(1)
    assert (row["subtotal_cents"], row["tax_cents"], row["total_cents"]) == (100, 1, 101)
