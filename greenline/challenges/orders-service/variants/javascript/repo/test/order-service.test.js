'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { InsufficientStock, Inventory } = require('../src/inventory')
const { OrderService } = require('../src/service')

function createBarrier(count) {
  let arrived = 0
  let release
  const ready = new Promise((resolve) => {
    release = resolve
  })
  return async () => {
    arrived += 1
    if (arrived === count) release()
    await ready
  }
}

function makeService(stock = 10, { authorize, beforeCheckout } = {}) {
  const inventory = new Inventory(authorize)
  if (stock) inventory.addStock('GPU-4090', stock)
  return new OrderService(inventory, beforeCheckout)
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

test('rejects non-positive order quantity', () => {
  const service = makeService()

  assert.throws(() => service.createOrder('GPU-4090', 0, 100), /quantity must be positive/)
  assert.equal(service.orders.size, 0)
})

test('rejects a blank SKU', () => {
  const service = makeService()

  assert.throws(() => service.createOrder('  ', 1, 100), /sku must not be blank/)
  assert.equal(service.orders.size, 0)
})

for (const unitPriceCents of [0, -1]) {
  test(`rejects non-positive unit price ${unitPriceCents}`, () => {
    const service = makeService()

    assert.throws(
      () => service.createOrder('GPU-4090', 1, unitPriceCents),
      /unit price must be positive/,
    )
    assert.equal(service.orders.size, 0)
  })
}

test('applies discount boundaries without compounding', () => {
  const service = makeService()
  const below = service.createOrder('GPU-4090', 1, 4999)
  const fivePercent = service.createOrder('GPU-4090', 5, 1000)
  const tenPercent = service.createOrder('GPU-4090', 5, 2000)

  service.applyDiscount(below)
  service.applyDiscount(fivePercent)
  service.applyDiscount(tenPercent)
  service.applyDiscount(tenPercent)

  assert.deepEqual([below.discountCents, service.totalCents(below)], [0, 4999])
  assert.deepEqual([fivePercent.discountCents, service.totalCents(fivePercent)], [250, 4750])
  assert.deepEqual([tenPercent.discountCents, service.totalCents(tenPercent)], [1000, 9000])
})

test('insufficient reservation leaves stock unchanged', async () => {
  const inventory = new Inventory()
  inventory.addStock('GPU', 2)

  await assert.rejects(inventory.reserve('GPU', 3), InsufficientStock)

  assert.equal(inventory.available('GPU'), 2)
})

test('rejects non-positive reservation quantity', async () => {
  const inventory = new Inventory()
  inventory.addStock('GPU', 2)

  await assert.rejects(inventory.reserve('GPU', 0), /quantity must be positive/)

  assert.equal(inventory.available('GPU'), 2)
})

test('keeps authorization for different SKUs concurrent', async () => {
  const authorize = createBarrier(2)
  const inventory = new Inventory(authorize)
  inventory.addStock('GPU', 1)
  inventory.addStock('CPU', 1)

  await Promise.all([inventory.reserve('GPU', 1), inventory.reserve('CPU', 1)])

  assert.equal(inventory.available('GPU'), 0)
  assert.equal(inventory.available('CPU'), 0)
})

const inventoryRaces = [
  ['last unit', 1, 1, 4],
  ['pairs', 4, 2, 4],
  ['remainder', 10, 4, 4],
]

for (const [name, stock, quantity, buyers] of inventoryRaces) {
  test(`never oversells ${name} during concurrent reservations`, async () => {
    const inventory = new Inventory(createBarrier(buyers))
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
  })
}

test('retrying a completed checkout does not reserve twice', async () => {
  const service = makeService(2)
  const order = service.createOrder('GPU-4090', 1, 100)

  assert.equal(await service.checkout(order), true)
  assert.equal(await service.checkout(order), true)

  assert.equal(order.status, 'completed')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})

test('rejected checkout remains terminal after restock', async () => {
  const service = makeService(0)
  const order = service.createOrder('GPU-4090', 1, 100)

  assert.equal(await service.checkout(order), false)
  service.inventory.addStock('GPU-4090', 1)
  assert.equal(await service.checkout(order), false)

  assert.equal(order.status, 'rejected')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})

test('authorization error restores created state without consuming stock', async () => {
  const service = makeService(1, {
    authorize: async () => {
      throw new Error('payment network unavailable')
    },
  })
  const order = service.createOrder('GPU-4090', 1, 100)

  await assert.rejects(service.checkout(order), /payment network unavailable/)

  assert.equal(order.status, 'created')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})

test('concurrent retries of one order reserve once', async () => {
  const service = makeService(2, { beforeCheckout: createBarrier(2) })
  const order = service.createOrder('GPU-4090', 1, 100)

  const results = await Promise.all([service.checkout(order), service.checkout(order)])

  assert.deepEqual(results, [true, true])
  assert.equal(order.status, 'completed')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})

test('cancelling a completed order restocks inventory', async () => {
  const service = makeService(1)
  const order = service.createOrder('GPU-4090', 1, 100)
  assert.equal(await service.checkout(order), true)

  assert.equal(await service.cancel(order), true)

  assert.equal(order.status, 'cancelled')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})

test('cannot cancel an order that never completed', async () => {
  const service = makeService(1)
  const order = service.createOrder('GPU-4090', 1, 100)

  assert.equal(await service.cancel(order), false)

  assert.equal(order.status, 'created')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})

test('repeated cancellation does not restock twice', async () => {
  const service = makeService(1)
  const order = service.createOrder('GPU-4090', 1, 100)
  assert.equal(await service.checkout(order), true)

  assert.equal(await service.cancel(order), true)
  assert.equal(await service.cancel(order), false)

  assert.equal(order.status, 'cancelled')
  assert.equal(service.inventory.available('GPU-4090'), 1)
})
