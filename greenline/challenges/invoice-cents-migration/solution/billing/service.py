"""Invoice writes and the online cents backfill."""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, ROUND_HALF_UP

from billing.db import connect


def cents(value: str) -> int:
    return int((Decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def representations(amount: str, tax_amount: str) -> tuple[int, int, int]:
    total = cents(amount)
    tax = cents(tax_amount)
    return total - tax, tax, total


class InvoiceDatabase:
    def __init__(self, path: str) -> None:
        self.connection = connect(path)

    def seed_legacy(self, invoice_id: int, amount: str, tax_amount: str) -> None:
        self.connection.execute(
            "INSERT INTO invoices (id, amount, tax_amount) VALUES (?, ?, ?)",
            (invoice_id, amount, tax_amount),
        )

    def create_invoice(self, invoice_id: int, amount: str, tax_amount: str) -> None:
        subtotal, tax, total = representations(amount, tax_amount)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT INTO invoices "
                "(id, amount, tax_amount, subtotal_cents, tax_cents, total_cents) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (invoice_id, amount, tax_amount, subtotal, tax, total),
            )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

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
        connection.execute("BEGIN IMMEDIATE")
        try:
            state = connection.execute(
                "SELECT last_id FROM migration_state WHERE name = 'invoice-cents'"
            ).fetchone()
            last_id = int(state["last_id"])
            rows = connection.execute(
                "SELECT id, amount, tax_amount FROM invoices "
                "WHERE total_cents IS NULL AND id > ? ORDER BY id LIMIT ?",
                (last_id, batch_size),
            ).fetchall()

            # A stale cursor is evidence, not proof. Wrap to remaining rows instead
            # of declaring completion while an old-writer row is still unmigrated.
            if not rows:
                rows = connection.execute(
                    "SELECT id, amount, tax_amount FROM invoices "
                    "WHERE total_cents IS NULL ORDER BY id LIMIT ?",
                    (batch_size,),
                ).fetchall()

            for row in rows:
                subtotal, tax, total = representations(row["amount"], row["tax_amount"])
                connection.execute(
                    "UPDATE invoices SET subtotal_cents = ?, tax_cents = ?, total_cents = ? "
                    "WHERE id = ? AND total_cents IS NULL",
                    (subtotal, tax, total, row["id"]),
                )

            if before_commit is not None:
                before_commit()

            remaining = connection.execute(
                "SELECT 1 FROM invoices WHERE total_cents IS NULL LIMIT 1"
            ).fetchone()
            next_last_id = max((int(row["id"]) for row in rows), default=last_id)
            connection.execute(
                "UPDATE migration_state SET last_id = ?, completed = ? "
                "WHERE name = 'invoice-cents'",
                (next_last_id, int(remaining is None)),
            )
            connection.execute("COMMIT")
            return len(rows)
        except Exception:
            connection.execute("ROLLBACK")
            raise
