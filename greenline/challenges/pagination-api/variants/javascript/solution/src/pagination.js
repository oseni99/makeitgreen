'use strict'

class Event {
  constructor({ id, createdAt, message }) {
    this.id = id
    this.createdAt = createdAt
    this.message = message
  }

  serialize() {
    return { id: this.id, createdAt: this.createdAt.toISOString(), message: this.message }
  }
}

class EventStore {
  constructor(events = []) {
    this.events = [...events]
  }

  add(event) {
    if (this.events.some((existing) => existing.id === event.id)) {
      throw new Error(`duplicate event id: ${event.id}`)
    }
    this.events.push(event)
  }

  all() {
    return [...this.events]
  }
}

function encodeCursor(event) {
  const payload = { version: 1, createdAt: event.createdAt.toISOString(), id: event.id }
  return Buffer.from(JSON.stringify(payload)).toString('base64url')
}

function decodeCursor(cursor) {
  try {
    const payload = JSON.parse(Buffer.from(cursor, 'base64url').toString('utf8'))
    if (payload.version !== 1 || typeof payload.id !== 'string') throw new Error()
    const timestamp = Date.parse(payload.createdAt)
    if (!Number.isFinite(timestamp)) throw new Error()
    return { timestamp, id: payload.id }
  } catch {
    throw new Error('invalid cursor')
  }
}

function descending(a, b) {
  return b.createdAt.getTime() - a.createdAt.getTime() || b.id.localeCompare(a.id)
}

class EventPager {
  constructor(store) {
    this.store = store
  }

  page({ limit, cursor = null }) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
      throw new Error('limit must be between 1 and 100')
    }

    let ordered = this.store.all().sort(descending)
    if (cursor) {
      const boundary = decodeCursor(cursor)
      ordered = ordered.filter((event) => {
        const timestamp = event.createdAt.getTime()
        return timestamp < boundary.timestamp || (timestamp === boundary.timestamp && event.id < boundary.id)
      })
    }
    const window = ordered.slice(0, limit)
    return {
      items: window.map((event) => event.serialize()),
      nextCursor: ordered.length > window.length ? encodeCursor(window.at(-1)) : null,
    }
  }
}

module.exports = { Event, EventPager, EventStore }
