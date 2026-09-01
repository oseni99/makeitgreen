"""SQLite persistence primitives. Transaction ownership belongs to callers."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from commerce.models import Order, OutboxEvent


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                total_cents INTEGER NOT NULL CHECK (total_cents > 0)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE,
                order_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                published_at TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            );
            """
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()

    def insert_order(self, order: Order) -> None:
        self.conn.execute(
            "INSERT INTO orders (id, customer_id, total_cents) VALUES (?, ?, ?)",
            (order.id, order.customer_id, order.total_cents),
        )

    def get_order(self, order_id: str) -> Order | None:
        row = self.conn.execute(
            "SELECT id, customer_id, total_cents FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        return Order(**dict(row)) if row else None

    def list_orders(self) -> list[Order]:
        rows = self.conn.execute(
            "SELECT id, customer_id, total_cents FROM orders ORDER BY id"
        ).fetchall()
        return [Order(**dict(row)) for row in rows]

    def enqueue(self, event: OutboxEvent, order_id: str) -> None:
        self.conn.execute(
            """INSERT INTO outbox (id, order_id, topic, payload_json, published_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                event.id,
                order_id,
                event.topic,
                json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
                event.published_at,
            ),
        )

    def pending_events(self, limit: int = 100) -> list[OutboxEvent]:
        rows = self.conn.execute(
            """SELECT id, topic, payload_json, published_at
               FROM outbox WHERE published_at IS NULL
               ORDER BY sequence LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            OutboxEvent(
                id=row["id"],
                topic=row["topic"],
                payload=json.loads(row["payload_json"]),
                published_at=row["published_at"],
            )
            for row in rows
        ]

    def mark_published(self, event_id: str, published_at: str) -> None:
        self.conn.execute(
            "UPDATE outbox SET published_at = ? WHERE id = ? AND published_at IS NULL",
            (published_at, event_id),
        )

    def get_event(self, event_id: str) -> OutboxEvent | None:
        row = self.conn.execute(
            "SELECT id, topic, payload_json, published_at FROM outbox WHERE id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return OutboxEvent(
            id=row["id"],
            topic=row["topic"],
            payload=json.loads(row["payload_json"]),
            published_at=row["published_at"],
        )

    def outbox_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
