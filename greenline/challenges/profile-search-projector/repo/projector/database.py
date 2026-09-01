from __future__ import annotations

import sqlite3


class Database:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.executescript(
            """
            CREATE TABLE changes (
                change_id INTEGER PRIMARY KEY,
                profile_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                display_name TEXT,
                visible INTEGER NOT NULL
            );
            CREATE TABLE search_profiles (
                profile_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            );
            CREATE TABLE projector_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                checkpoint INTEGER NOT NULL
            );
            INSERT INTO projector_state VALUES (1, 0);
            """
        )
        self.connection.commit()

    def change(self, change_id: int, profile_id: str, operation: str, name: str | None, *, visible: bool = True) -> None:
        self.connection.execute(
            "INSERT INTO changes VALUES (?, ?, ?, ?, ?)",
            (change_id, profile_id, operation, name, int(visible)),
        )
        self.connection.commit()

    def reveal(self, change_id: int) -> None:
        self.connection.execute("UPDATE changes SET visible = 1 WHERE change_id = ?", (change_id,))
        self.connection.commit()

    def checkpoint(self) -> int:
        return self.connection.execute("SELECT checkpoint FROM projector_state").fetchone()[0]

    def projection(self) -> dict[str, str]:
        return dict(self.connection.execute(
            "SELECT profile_id, display_name FROM search_profiles ORDER BY profile_id"
        ).fetchall())
