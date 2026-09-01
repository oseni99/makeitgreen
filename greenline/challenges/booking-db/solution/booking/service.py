"""Show booking service — seats live in SQLite."""
from __future__ import annotations

import sqlite3

from booking.db import connect
from booking.errors import AlreadyBooked, NotFound, SoldOut


class BookingService:
    def __init__(self, db_path: str) -> None:
        self.conn = connect(db_path)

    def create_show(self, show_id: str, title: str, seats: int) -> None:
        if seats < 0:
            raise ValueError("seats cannot be negative")
        self.conn.execute(
            "INSERT INTO shows (id, title, seats_left) VALUES (?, ?, ?)",
            (show_id, title, seats),
        )

    def seats_left(self, show_id: str) -> int:
        row = self.conn.execute(
            "SELECT seats_left FROM shows WHERE id = ?",
            (show_id,),
        ).fetchone()
        if row is None:
            raise NotFound(show_id)
        return int(row["seats_left"])

    def book(self, show_id: str, user_id: str, seats: int = 1) -> int:
        """Reserve seats for a user. Returns the new booking id."""
        if seats <= 0:
            raise ValueError("seats must be positive")

        # BEGIN IMMEDIATE takes the write lock up front so the check and the
        # mutations cannot interleave with another booker's transaction.
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            left = self.seats_left(show_id)
            if left < seats:
                raise SoldOut(show_id)

            try:
                cur = self.conn.execute(
                    "INSERT INTO bookings (show_id, user_id, seats) "
                    "VALUES (?, ?, ?)",
                    (show_id, user_id, seats),
                )
            except sqlite3.IntegrityError as exc:
                raise AlreadyBooked(show_id, user_id) from exc

            self.conn.execute(
                "UPDATE shows SET seats_left = seats_left - ? WHERE id = ?",
                (seats, show_id),
            )
            self.conn.execute("COMMIT")
            return int(cur.lastrowid)
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def cancel(self, booking_id: int) -> None:
        """Cancel a booking and return its seats to the show."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT show_id, seats FROM bookings WHERE id = ?",
                (booking_id,),
            ).fetchone()
            if row is None:
                raise NotFound(booking_id)

            self.conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            self.conn.execute(
                "UPDATE shows SET seats_left = seats_left + ? WHERE id = ?",
                (int(row["seats"]), row["show_id"]),
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def bookings_for(self, show_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, user_id, seats FROM bookings "
            "WHERE show_id = ? ORDER BY id",
            (show_id,),
        ).fetchall()
        return [
            {"id": int(r["id"]), "user_id": r["user_id"], "seats": int(r["seats"])}
            for r in rows
        ]
