'use strict'

class InsufficientStock extends Error {}

class Inventory {
  constructor(authorize = async () => {}) {
    this._stock = new Map()
    this._authorize = authorize
    this._tails = new Map()
  }

  addStock(sku, quantity) {
    this._stock.set(sku, (this._stock.get(sku) ?? 0) + quantity)
  }

  available(sku) {
    return this._stock.get(sku) ?? 0
  }

  async reserve(sku, quantity) {
    const previous = this._tails.get(sku) ?? Promise.resolve()
    let release
    const ticket = new Promise((resolve) => {
      release = resolve
    })
    const tail = previous.then(() => ticket)
    this._tails.set(sku, tail)

    await previous
    try {
      if (this.available(sku) < quantity) {
        throw new InsufficientStock(sku)
      }
      await this._authorize(sku)
      this._stock.set(sku, this.available(sku) - quantity)
    } finally {
      release()
      if (this._tails.get(sku) === tail) {
        this._tails.delete(sku)
      }
    }
  }
}

module.exports = { InsufficientStock, Inventory }
