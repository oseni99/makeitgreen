"""Invariants for the SQLite booking booth.

These tests are the schema review. Read the assertions before editing code.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from booking.errors import AlreadyBooked, NotFound, SoldOut
from booking.service import BookingService


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    # File-backed (not :memory:) so concurrent threads share one database.
    return str(tmp_path / "booking.db")


@pytest.fixture
def svc(db_path: str) -> BookingService:
    s = BookingService(db_path)
    s.create_show("hamlet", "Hamlet", seats=10)
    return s


def test_book_reduces_inventory(svc: BookingService) -> None:
    booking_id = svc.book("hamlet", "alice", seats=2)
    assert booking_id > 0
    assert svc.seats_left("hamlet") == 8
    assert svc.bookings_for("hamlet") == [
        {"id": booking_id, "user_id": "alice", "seats": 2}
    ]


def test_rejects_when_sold_out(svc: BookingService) -> None:
    svc.book("hamlet", "alice", seats=10)
    with pytest.raises(SoldOut):
        svc.book("hamlet", "bob", seats=1)
    assert svc.seats_left("hamlet") == 0
    assert len(svc.bookings_for("hamlet")) == 1


def test_cancel_restores_seats(svc: BookingService) -> None:
    """Cancel must delete the booking AND put the seats back."""
    booking_id = svc.book("hamlet", "alice", seats=3)
    assert svc.seats_left("hamlet") == 7

    svc.cancel(booking_id)

    assert svc.seats_left("hamlet") == 10
    assert svc.bookings_for("hamlet") == []
    with pytest.raises(NotFound):
        svc.cancel(booking_id)


def test_one_booking_per_user_per_show(svc: BookingService) -> None:
    """A user may hold at most one booking row for a given show."""
    svc.book("hamlet", "alice", seats=1)
    with pytest.raises(AlreadyBooked):
        svc.book("hamlet", "alice", seats=1)
    assert svc.seats_left("hamlet") == 9
    assert len(svc.bookings_for("hamlet")) == 1


def test_concurrent_last_seat_is_atomic(db_path: str) -> None:
    """Exactly one of N concurrent attempts may take the final seat.

    Without a proper write transaction, check-then-insert races let several
    buyers "win" and drive seats_left negative.

    Each thread opens its own connection (separate BookingService) so the race
    is against the database file — a single shared connection would serialize
    statements and hide the bug.
    """
    BookingService(db_path).create_show("encore", "Encore Night", seats=1)

    n = 8
    barrier = threading.Barrier(n)
    winners: list[int] = []
    lock = threading.Lock()

    def attempt(user_id: str) -> None:
        svc = BookingService(db_path)
        barrier.wait()
        try:
            booking_id = svc.book("encore", user_id, seats=1)
        except SoldOut:
            return
        with lock:
            winners.append(booking_id)

    threads = [
        threading.Thread(target=attempt, args=(f"fan-{i}",)) for i in range(n)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    svc = BookingService(db_path)
    assert len(winners) == 1, f"expected 1 winner, got {len(winners)}: {winners}"
    assert svc.seats_left("encore") == 0
    assert len(svc.bookings_for("encore")) == 1
    assert sum(b["seats"] for b in svc.bookings_for("encore")) == 1
