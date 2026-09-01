"""Invoice writes and the online cents backfill."""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, ROUND_HALF_UP

from billing.db import connect


def cents(value: str) -> int:
    return int((Decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class InvoiceDatabase:
    def __init__(self, path: str) -> None:
        self.connection = connect(path)

    def seed_legacy(self, invoice_id: int, amount: str, tax_amount: str) -> None:
        self.connection.execute(
            "INSERT INTO invoices (id, amount, tax_amount) VALUES (?, ?, ?)",
            (invoice_id, amount, tax_amount),
        )

    def create_invoice(self, invoice_id: int, amount: str, tax_amount: str) -> None:
        # BUG: live traffic still writes only the legacy representation.
        self.seed_legacy(invoice_id, amount, tax_amount)

    def invoice(self, invoice_id: int) -> dict:
        row = self.connection.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if row is None:
            raise LookupError(invoice_id)
        return dict(row)

    def state(self) -> dict:
        row = self.connection.execute(
            "SELECT last_id, completed FROM migration_state WHERE name = 'invoice-cents'"
        ).fetchone()
        return {"last_id": int(row["last_id"]), "completed": bool(row["completed"])}

    def force_state(self, last_id: int, completed: bool) -> None:
        self.connection.execute(
            "UPDATE migration_state SET last_id = ?, completed = ? "
            "WHERE name = 'invoice-cents'",
            (last_id, int(completed)),
        )

    def unmigrated_ids(self) -> list[int]:
        rows = self.connection.execute(
            "SELECT id FROM invoices WHERE total_cents IS NULL ORDER BY id"
        ).fetchall()
        return [int(row["id"]) for row in rows]


class MigrationRunner:
    def __init__(self, database: InvoiceDatabase) -> None:
        self.database = database

    def run_batch(
        self,
        batch_size: int,
        *,
        before_commit: Callable[[], None] | None = None,
    ) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        connection = self.database.connection
        state = self.database.state()

        # BUG: last_id is incorrectly used as an OFFSET over a result set that
        # shrinks as rows are migrated, so later rows can be skipped.
        rows = connection.execute(
            "SELECT id, amount, tax_amount FROM invoices "
            "WHERE total_cents IS NULL ORDER BY id LIMIT ? OFFSET ?",
            (batch_size, state["last_id"]),
        ).fetchall()
        for row in rows:
            total = cents(row["amount"])
            tax = cents(row["tax_amount"])
            connection.execute(
                "UPDATE invoices SET subtotal_cents = ?, tax_cents = ?, total_cents = ? "
                "WHERE id = ?",
                (total - tax, tax, total, row["id"]),
            )

        if before_commit is not None:
            before_commit()

        connection.execute(
            "UPDATE migration_state SET last_id = ?, completed = ? "
            "WHERE name = 'invoice-cents'",
            (state["last_id"] + len(rows), int(len(rows) < batch_size)),
        )
        return len(rows)
