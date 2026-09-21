'use strict'

class InsufficientStock extends Error {}

class Inventory {
  constructor(authorize = async () => {}) {
    this._stock = new Map()
    this._authorize = authorize
    this._tails = new Map()
  }

  addStock(sku, quantity) {
    if (quantity <= 0) throw new RangeError('quantity must be positive')
    this._stock.set(sku, (this._stock.get(sku) ?? 0) + quantity)
  }

  available(sku) {
    return this._stock.get(sku) ?? 0
  }

  async _withSkuLock(sku, action) {
    const previous = this._tails.get(sku) ?? Promise.resolve()
    let release
    const ticket = new Promise((resolve) => {
      release = resolve
    })
    const tail = previous.then(() => ticket)
    this._tails.set(sku, tail)

    await previous
    try {
      return await action()
    } finally {
      release()
      if (this._tails.get(sku) === tail) this._tails.delete(sku)
    }
  }

  async reserve(sku, quantity) {
    if (quantity <= 0) throw new RangeError('quantity must be positive')
    await this._authorize(sku)
    return this._withSkuLock(sku, async () => {
      if (this.available(sku) < quantity) {
        throw new InsufficientStock(sku)
      }
      this._stock.set(sku, this.available(sku) - quantity)
    })
  }

  async release(sku, quantity) {
    if (quantity <= 0) throw new RangeError('quantity must be positive')
    return this._withSkuLock(sku, async () => {
      this._stock.set(sku, this.available(sku) + quantity)
    })
  }
}

module.exports = { InsufficientStock, Inventory }
