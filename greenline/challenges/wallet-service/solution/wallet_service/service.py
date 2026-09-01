"""Wallet balances and transfers.

Fee schedule: transfers cost 1% of the amount, minimum 1 cent, paid by the
sender on top of the transferred amount. All amounts are integer cents.
"""
from __future__ import annotations

from wallet_service.errors import AccountNotFound, InsufficientFunds, InvalidAmount

FEE_RATE = 0.01


class WalletService:
    def __init__(self) -> None:
        self._balances: dict[str, int] = {}
        self._fees_collected = 0

    def open_account(self, account_id: str) -> None:
        self._balances.setdefault(account_id, 0)

    def balance(self, account_id: str) -> int:
        if account_id not in self._balances:
            raise AccountNotFound(account_id)
        return self._balances[account_id]

    def deposit(self, account_id: str, amount_cents: int) -> int:
        if account_id not in self._balances:
            raise AccountNotFound(account_id)
        if amount_cents <= 0:
            raise InvalidAmount(amount_cents)
        self._balances[account_id] += amount_cents
        return self._balances[account_id]

    def transfer_fee(self, amount_cents: int) -> int:
        """1% of the amount, minimum 1 cent."""
        return max(1, int(amount_cents * FEE_RATE))

    def transfer(self, src: str, dst: str, amount_cents: int) -> int:
        """Move amount from src to dst. Sender pays amount + fee.

        Returns the fee charged.
        """
        if src not in self._balances or dst not in self._balances:
            raise AccountNotFound(src if src not in self._balances else dst)
        if amount_cents <= 0:
            raise InvalidAmount(amount_cents)

        fee = self.transfer_fee(amount_cents)
        if self._balances[src] < amount_cents + fee:
            raise InsufficientFunds(src)

        self._balances[src] -= amount_cents + fee
        self._balances[dst] += amount_cents
        self._fees_collected += fee
        return fee

    @property
    def fees_collected(self) -> int:
        return self._fees_collected
