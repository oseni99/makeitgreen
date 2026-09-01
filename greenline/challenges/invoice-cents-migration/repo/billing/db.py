"""SQLite schema for the expanded invoice representation."""
from __future__ import annotations

import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    amount TEXT NOT NULL,
    tax_amount TEXT NOT NULL,
    subtotal_cents INTEGER,
    tax_cents INTEGER,
    total_cents INTEGER
);

CREATE TABLE IF NOT EXISTS migration_state (
    name TEXT PRIMARY KEY,
    last_id INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO migration_state (name, last_id, completed)
VALUES ('invoice-cents', 0, 0);
"""


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    return connection
