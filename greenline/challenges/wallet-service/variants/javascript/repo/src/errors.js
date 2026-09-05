'use strict'

class WalletError extends Error {}
class AccountNotFound extends WalletError {}
class InsufficientFunds extends WalletError {}
class InvalidAmount extends WalletError {}

module.exports = { AccountNotFound, InsufficientFunds, InvalidAmount, WalletError }
