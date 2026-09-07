'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { InsufficientStock, Inventory } = require('../src/inventory')
const { OrderService } = require('../src/service')

function makeService(stock = 10, authorize) {
  const inventory = new Inventory(authorize)
  inventory.addStock('GPU-4090', stock)
  return new OrderService(inventory)
}

test('creates and registers an order', () => {
  const service = makeService()
  const order = service.createOrder('GPU-4090', 2, 1999)

  assert.equal(order.sku, 'GPU-4090')
  assert.equal(order.quantity, 2)
  assert.equal(order.subtotalCents, 3998)
  assert.equal(order.status, 'created')
  assert.equal(service.orders.get(order.id), order)
})

test('applies the quantity discount boundaries', () => {
  const service = makeService()
  const below = service.createOrder('GPU-4090', 2, 2000)
  const fivePercent = service.createOrder('GPU-4090', 3, 2000)
  const tenPercent = service.createOrder('GPU-4090', 5, 2000)

  service.applyDiscount(below)
  service.applyDiscount(fivePercent)
  service.applyDiscount(tenPercent)

  assert.deepEqual([below.discountCents, service.totalCents(below)], [0, 4000])
  assert.deepEqual([fivePercent.discountCents, service.totalCents(fivePercent)], [300, 5700])
  assert.deepEqual([tenPercent.discountCents, service.totalCents(tenPercent)], [1000, 9000])
})

test('insufficient reservation leaves stock unchanged', async () => {
  const inventory = new Inventory()
  inventory.addStock('GPU', 2)

  await assert.rejects(inventory.reserve('GPU', 3), InsufficientStock)

  assert.equal(inventory.available('GPU'), 2)
})

test('unexpected authorization failure propagates without consuming stock', async () => {
  const authorizationError = new Error('payment network unavailable')
  const service = makeService(1, async () => {
    throw authorizationError
  })
  const order = service.createOrder('GPU-4090', 1, 100)

  await assert.rejects(service.checkout(order), authorizationError)

  assert.equal(order.status, 'created')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})

test('keeps authorization for different SKUs concurrent', async () => {
  const entered = []
  const releases = new Map()
  const authorize = (sku) =>
    new Promise((resolve) => {
      entered.push(sku)
      releases.set(sku, resolve)
    })
  const inventory = new Inventory(authorize)
  inventory.addStock('GPU', 1)
  inventory.addStock('CPU', 1)

  const gpu = inventory.reserve('GPU', 1)
  const cpu = inventory.reserve('CPU', 1)
  await new Promise((resolve) => setImmediate(resolve))

  assert.deepEqual(entered.sort(), ['CPU', 'GPU'])
  releases.get('GPU')()
  releases.get('CPU')()
  await Promise.all([gpu, cpu])
})

const inventoryRaces = [
  ['last unit', 1, 1, 8],
  ['two units', 2, 1, 8],
  ['five units', 5, 1, 12],
  ['pairs', 4, 2, 8],
  ['three pairs', 6, 2, 8],
  ['triples', 9, 3, 8],
  ['remainder', 10, 4, 8],
]

for (const [name, stock, quantity, buyers] of inventoryRaces) {
  test(`keeps ${name} atomic during concurrent inventory reservations`, async () => {
    const inventory = new Inventory()
    inventory.addStock('GPU', stock)

    const results = await Promise.all(
      Array.from({ length: buyers }, async () => {
        try {
          await inventory.reserve('GPU', quantity)
          return true
        } catch (error) {
          if (error instanceof InsufficientStock) return false
          throw error
        }
      }),
    )
    const expectedSuccesses = Math.min(buyers, Math.floor(stock / quantity))

    assert.equal(results.filter(Boolean).length, expectedSuccesses)
    assert.equal(inventory.available('GPU'), stock - expectedSuccesses * quantity)
    assert.ok(inventory.available('GPU') >= 0)
  })
}

const checkoutRaces = [
  ['single winner', 1, 1, 8],
  ['three winners', 3, 1, 10],
  ['two pairs', 4, 2, 8],
  ['three pairs', 6, 2, 8],
  ['triple remainder', 8, 3, 8],
  ['quad remainder', 10, 4, 8],
]

for (const [name, stock, quantity, buyers] of checkoutRaces) {
  test(`completes only funded orders for ${name}`, async () => {
    const service = makeService(stock)
    const orders = Array.from({ length: buyers }, () =>
      service.createOrder('GPU-4090', quantity, 100),
    )

    const results = await Promise.all(orders.map((order) => service.checkout(order)))
    const expectedSuccesses = Math.min(buyers, Math.floor(stock / quantity))

    assert.equal(results.filter(Boolean).length, expectedSuccesses)
    assert.equal(orders.filter((order) => order.status === 'paid').length, expectedSuccesses)
    assert.equal(orders.filter((order) => order.status === 'rejected').length, buyers - expectedSuccesses)
    assert.equal(
      service.inventory.available('GPU-4090'),
      stock - expectedSuccesses * quantity,
    )
  })
}
