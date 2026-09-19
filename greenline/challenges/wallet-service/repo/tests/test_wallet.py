import pytest

from wallet_service.errors import InsufficientFunds, InvalidAmount
from wallet_service.service import WalletService


@pytest.fixture
def svc() -> WalletService:
    s = WalletService()
    s.open_account("alice")
    s.open_account("bob")
    s.deposit("alice", 10_000)  # $100.00
    return s


def test_deposit_and_balance(svc: WalletService) -> None:
    assert svc.balance("alice") == 10_000
    assert svc.balance("bob") == 0
    svc.deposit("bob", 250)
    assert svc.balance("bob") == 250


def test_rejects_invalid_amounts(svc: WalletService) -> None:
    with pytest.raises(InvalidAmount):
        svc.deposit("alice", 0)
    with pytest.raises(InvalidAmount):
        svc.transfer("alice", "bob", -5)


def test_simple_transfer(svc: WalletService) -> None:
    fee = svc.transfer("alice", "bob", 5_000)
    assert fee == 50  # 1% of $50.00
    assert svc.balance("bob") == 5_000
    assert svc.balance("alice") == 10_000 - 5_000 - 50
    assert svc.fees_collected == 50


def test_minimum_fee_is_one_cent(svc: WalletService) -> None:
    """Fee schedule: 1% of the amount, MINIMUM 1 cent."""
    fee = svc.transfer("alice", "bob", 50)  # 1% of 50c rounds to 0 — must charge 1c
    assert fee == 1, f"expected minimum fee of 1 cent, got {fee}"
    assert svc.balance("alice") == 10_000 - 50 - 1


def test_transfer_cannot_overdraft(svc: WalletService) -> None:
    """Sender must cover amount + fee. Balances may never go negative."""
    # alice has exactly 10_000; amount 10_000 + fee 100 exceeds her balance.
    with pytest.raises(InsufficientFunds):
        svc.transfer("alice", "bob", 10_000)
    assert svc.balance("alice") == 10_000, "failed transfer must not touch balances"
    assert svc.balance("bob") == 0
    assert svc.fees_collected == 0


@pytest.mark.parametrize("amount", [1, 2, 25, 50, 99])
def test_each_sub_dollar_transfer_charges_minimum_fee(
    svc: WalletService,
    amount: int,
) -> None:
    before = svc.balance("alice")
    assert svc.transfer("alice", "bob", amount) == 1
    assert svc.balance("alice") == before - amount - 1


@pytest.mark.parametrize("amount", [9_902, 9_950, 9_998, 9_999, 10_000])
def test_sender_must_cover_amount_plus_fee_without_partial_mutation(
    svc: WalletService,
    amount: int,
) -> None:
    before = (svc.balance("alice"), svc.balance("bob"), svc.fees_collected)
    with pytest.raises(InsufficientFunds):
        svc.transfer("alice", "bob", amount)
    assert (svc.balance("alice"), svc.balance("bob"), svc.fees_collected) == before
