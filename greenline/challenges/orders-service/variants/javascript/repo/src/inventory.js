'use strict'

class InsufficientStock extends Error {}

class Inventory {
  constructor(authorize = async () => {}) {
    this._stock = new Map()
    this._authorize = authorize
  }

  addStock(sku, quantity) {
    this._stock.set(sku, (this._stock.get(sku) ?? 0) + quantity)
  }

  available(sku) {
    return this._stock.get(sku) ?? 0
  }

  async reserve(sku, quantity) {
    if (this.available(sku) < quantity) {
      throw new InsufficientStock(sku)
    }

    // Authorization yields to other requests between the stock check and write.
    await this._authorize(sku)
    this._stock.set(sku, this.available(sku) - quantity)
  }

  async release(sku, quantity) {
    this._stock.set(sku, this.available(sku) + quantity)
  }
}

module.exports = { InsufficientStock, Inventory }
