'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { InsufficientFunds, InvalidAmount } = require('../src/errors')
const { WalletService } = require('../src/service')

function service() {
  const wallet = new WalletService()
  wallet.openAccount('alice')
  wallet.openAccount('bob')
  wallet.deposit('alice', 10_000)
  return wallet
}

test('deposits and reads balances', () => {
  const wallet = service()
  assert.equal(wallet.balance('alice'), 10_000)
  assert.equal(wallet.deposit('bob', 250), 250)
})

test('rejects invalid amounts', () => {
  const wallet = service()
  assert.throws(() => wallet.deposit('alice', 0), InvalidAmount)
  assert.throws(() => wallet.transfer('alice', 'bob', -5), InvalidAmount)
})

test('charges one percent for a normal transfer', () => {
  const wallet = service()
  assert.equal(wallet.transfer('alice', 'bob', 5_000), 50)
  assert.equal(wallet.balance('alice'), 4_950)
  assert.equal(wallet.balance('bob'), 5_000)
  assert.equal(wallet.feesCollected, 50)
})

test('charges the one-cent minimum fee', () => {
  const wallet = service()
  assert.equal(wallet.transfer('alice', 'bob', 50), 1)
  assert.equal(wallet.balance('alice'), 9_949)
})

test('cannot overdraft and leaves failed transfers untouched', () => {
  const wallet = service()
  assert.throws(() => wallet.transfer('alice', 'bob', 10_000), InsufficientFunds)
  assert.equal(wallet.balance('alice'), 10_000)
  assert.equal(wallet.balance('bob'), 0)
  assert.equal(wallet.feesCollected, 0)
})
