"""SQLite connection helpers and schema."""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS shows (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    seats_left INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    seats INTEGER NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open (or create) the booking database.

    isolation_level=None → autocommit; callers manage transactions explicitly.
    check_same_thread=False → the concurrent booking test shares one connection.
    """
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn
