class WalletError(Exception):
    pass


class AccountNotFound(WalletError):
    pass


class InsufficientFunds(WalletError):
    pass


class InvalidAmount(WalletError):
    pass
