'use strict'

const { InsufficientStock } = require('./inventory')

class OrderService {
  constructor(inventory, beforeCheckout = async () => {}) {
    this.inventory = inventory
    this.orders = new Map()
    this._nextId = 1
    this._beforeCheckout = beforeCheckout
    this._tails = new Map()
  }

  createOrder(sku, quantity, unitPriceCents) {
    if (typeof sku !== 'string' || sku.trim() === '') throw new TypeError('sku must not be blank')
    if (quantity <= 0) throw new RangeError('quantity must be positive')
    if (unitPriceCents <= 0) throw new RangeError('unit price must be positive')
    const order = {
      id: this._nextId++,
      sku,
      quantity,
      unitPriceCents,
      subtotalCents: quantity * unitPriceCents,
      discountCents: 0,
      status: 'created',
    }
    this.orders.set(order.id, order)
    return order
  }

  applyDiscount(order) {
    const rate = order.subtotalCents >= 10000 ? 0.1 : order.subtotalCents >= 5000 ? 0.05 : 0
    order.discountCents = Math.round(order.subtotalCents * rate)
    return order
  }

  totalCents(order) {
    return order.subtotalCents - order.discountCents
  }

  async _withOrderLock(orderId, action) {
    const previous = this._tails.get(orderId) ?? Promise.resolve()
    let release
    const ticket = new Promise((resolve) => {
      release = resolve
    })
    const tail = previous.then(() => ticket)
    this._tails.set(orderId, tail)

    await previous
    try {
      return await action()
    } finally {
      release()
      if (this._tails.get(orderId) === tail) this._tails.delete(orderId)
    }
  }

  async checkout(order) {
    await this._beforeCheckout(order)
    return this._withOrderLock(order.id, async () => {
      if (order.status === 'completed') return true
      if (order.status === 'rejected' || order.status === 'cancelled') return false

      order.status = 'processing'
      try {
        await this.inventory.reserve(order.sku, order.quantity)
      } catch (error) {
        if (error instanceof InsufficientStock) {
          order.status = 'rejected'
          return false
        }
        order.status = 'created'
        throw error
      }
      order.status = 'completed'
      return true
    })
  }

  async cancel(order) {
    return this._withOrderLock(order.id, async () => {
      if (order.status !== 'completed') return false
      await this.inventory.release(order.sku, order.quantity)
      order.status = 'cancelled'
      return true
    })
  }
}

module.exports = { OrderService }
