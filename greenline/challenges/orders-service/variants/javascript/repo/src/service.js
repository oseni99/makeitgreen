'use strict'

const { InsufficientStock } = require('./inventory')

class OrderService {
  constructor(inventory) {
    this.inventory = inventory
    this.orders = new Map()
    this._nextId = 1
  }

  createOrder(sku, quantity, unitPriceCents) {
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
    const rate = order.quantity >= 5 ? 0.1 : order.quantity >= 3 ? 0.05 : 0
    order.discountCents = Math.round(order.subtotalCents * rate)
    return order
  }

  totalCents(order) {
    return order.subtotalCents - order.discountCents
  }

  async checkout(order) {
    try {
      await this.inventory.reserve(order.sku, order.quantity)
    } catch (error) {
      if (error instanceof InsufficientStock) {
        order.status = 'rejected'
        return false
      }
      throw error
    }
    order.status = 'paid'
    return true
  }
}

module.exports = { OrderService }
