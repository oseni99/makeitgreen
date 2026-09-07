import threading
import time

import pytest

from transfer.accounts import AccountStore
from transfer.errors import InsufficientFunds, InvalidAmount
from transfer.service import TransferService


def make_service(alice: int = 10_000, bob: int = 10_000) -> TransferService:
    store = AccountStore()
    store.open("alice", alice)
    store.open("bob", bob)
    store.open("carol", 5_000)
    return TransferService(store), store


def test_simple_transfer() -> None:
    svc, store = make_service()
    svc.transfer("alice", "bob", 2_500)
    assert store.balance("alice") == 7_500
    assert store.balance("bob") == 12_500


def test_rejects_invalid_and_insufficient() -> None:
    svc, store = make_service(alice=100)
    with pytest.raises(InvalidAmount):
        svc.transfer("alice", "bob", 0)
    with pytest.raises(InvalidAmount):
        svc.transfer("alice", "alice", 10)
    with pytest.raises(InsufficientFunds):
        svc.transfer("alice", "bob", 500)


def test_concurrent_disjoint_transfers() -> None:
    """Transfers that don't share an account should both complete."""
    svc, store = make_service()
    barrier = threading.Barrier(2)

    def move(src: str, dst: str, amount: int) -> None:
        barrier.wait(timeout=2)
        svc.transfer(src, dst, amount)

    t1 = threading.Thread(target=move, args=("alice", "carol", 100), daemon=True)
    t2 = threading.Thread(target=move, args=("bob", "carol", 200), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive(), "alice→carol transfer hung"
    assert not t2.is_alive(), "bob→carol transfer hung"
    assert store.balance("alice") == 9_900
    assert store.balance("bob") == 9_800
    assert store.balance("carol") == 5_300


@pytest.mark.parametrize(
    "amount",
    [1, 10, 50, 100, 250, 500, 750, 1_000, 2_000, 3_000, 4_000, 5_000],
)
def test_concurrent_opposite_transfers(amount: int) -> None:
    """Opposite-direction transfers must not deadlock; net balances unchanged."""
    svc, store = make_service()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def move(src: str, dst: str, amount: int) -> None:
        try:
            barrier.wait(timeout=2)
            svc.transfer(src, dst, amount)
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=move, args=("alice", "bob", amount), daemon=True)
    t2 = threading.Thread(target=move, args=("bob", "alice", amount), daemon=True)
    t1.start()
    t2.start()
    deadline = time.monotonic() + 1.0
    for thread in (t1, t2):
        thread.join(timeout=max(0, deadline - time.monotonic()))

    assert not t1.is_alive(), "alice→bob transfer hung (deadlock?)"
    assert not t2.is_alive(), "bob→alice transfer hung (deadlock?)"
    assert errors == []
    assert store.balance("alice") == 10_000
    assert store.balance("bob") == 10_000
