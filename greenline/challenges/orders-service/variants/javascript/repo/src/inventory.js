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

    // Authorization yields to other checkout requests between the stock check
    // and its write. Several callers can therefore approve the same units.
    await this._authorize(sku)
    this._stock.set(sku, this.available(sku) - quantity)
  }
}

module.exports = { InsufficientStock, Inventory }
