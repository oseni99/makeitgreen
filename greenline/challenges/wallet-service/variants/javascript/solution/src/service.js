'use strict'

const { AccountNotFound, InsufficientFunds, InvalidAmount } = require('./errors')

const FEE_RATE = 0.01

class WalletService {
  constructor() {
    this.balances = new Map()
    this.feesCollected = 0
  }

  openAccount(accountId) {
    if (!this.balances.has(accountId)) this.balances.set(accountId, 0)
  }

  balance(accountId) {
    if (!this.balances.has(accountId)) throw new AccountNotFound(accountId)
    return this.balances.get(accountId)
  }

  deposit(accountId, amountCents) {
    if (!this.balances.has(accountId)) throw new AccountNotFound(accountId)
    if (amountCents <= 0) throw new InvalidAmount(String(amountCents))
    this.balances.set(accountId, this.balance(accountId) + amountCents)
    return this.balance(accountId)
  }

  transferFee(amountCents) {
    return Math.max(1, Math.trunc(amountCents * FEE_RATE))
  }

  transfer(source, destination, amountCents) {
    if (!this.balances.has(source)) throw new AccountNotFound(source)
    if (!this.balances.has(destination)) throw new AccountNotFound(destination)
    if (amountCents <= 0) throw new InvalidAmount(String(amountCents))

    const fee = this.transferFee(amountCents)
    if (this.balance(source) < amountCents + fee) throw new InsufficientFunds(source)

    this.balances.set(source, this.balance(source) - amountCents - fee)
    this.balances.set(destination, this.balance(destination) + amountCents)
    this.feesCollected += fee
    return fee
  }
}

module.exports = { WalletService }
