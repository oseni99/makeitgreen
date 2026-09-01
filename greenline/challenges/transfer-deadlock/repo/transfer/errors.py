"""Transfer domain errors."""


class AccountNotFound(Exception):
    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"account not found: {account_id}")


class InvalidAmount(Exception):
    def __init__(self, amount_cents: int) -> None:
        self.amount_cents = amount_cents
        super().__init__(f"invalid amount: {amount_cents}")


class InsufficientFunds(Exception):
    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"insufficient funds: {account_id}")
