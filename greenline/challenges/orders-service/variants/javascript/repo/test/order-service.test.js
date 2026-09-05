'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { Inventory } = require('../src/inventory')
const { OrderService } = require('../src/service')

function makeService(stock = 10, authorize) {
  const inventory = new Inventory(authorize)
  inventory.addStock('GPU-4090', stock)
  return new OrderService(inventory)
}

test('creates an order', () => {
  const service = makeService()
  const order = service.createOrder('GPU-4090', 2, 1999)

  assert.equal(order.subtotalCents, 3998)
  assert.equal(order.status, 'created')
  assert.equal(service.orders.get(order.id), order)
})

test('applies quantity discounts', () => {
  const service = makeService()
  const medium = service.createOrder('GPU-4090', 3, 2000)
  const large = service.createOrder('GPU-4090', 6, 2000)

  service.applyDiscount(medium)
  service.applyDiscount(large)

  assert.equal(medium.discountCents, 300)
  assert.equal(service.totalCents(medium), 5700)
  assert.equal(large.discountCents, 1200)
})

test('does not oversell during concurrent checkouts', async () => {
  const service = makeService(10)
  const orders = Array.from({ length: 50 }, () =>
    service.createOrder('GPU-4090', 1, 99_900),
  )

  const results = await Promise.all(orders.map((order) => service.checkout(order)))

  assert.equal(results.filter(Boolean).length, 10)
  assert.equal(service.inventory.available('GPU-4090'), 0)
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
