'use strict'

const { InsufficientStock } = require('./inventory')

class OrderService {
  constructor(inventory, beforeCheckout = async () => {}) {
    this.inventory = inventory
    this.orders = new Map()
    this._nextId = 1
    this._beforeCheckout = beforeCheckout
  }

  createOrder(sku, quantity, unitPriceCents) {
    if (quantity <= 0) throw new RangeError('quantity must be positive')
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

  async checkout(order) {
    await this._beforeCheckout(order)
    order.status = 'processing'
    try {
      await this.inventory.reserve(order.sku, order.quantity)
    } catch (error) {
      if (error instanceof InsufficientStock) {
        order.status = 'rejected'
        return false
      }
      throw error
    }
    order.status = 'completed'
    return true
  }

  async cancel(order) {
    order.status = 'cancelled'
    return true
  }
}

module.exports = { OrderService }
