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

function encodeOffset(offset) {
  return Buffer.from(JSON.stringify({ offset })).toString('base64url')
}

function decodeOffset(cursor) {
  try {
    const payload = JSON.parse(Buffer.from(cursor, 'base64url').toString('utf8'))
    if (!Number.isInteger(payload.offset) || payload.offset < 0) throw new Error()
    return payload.offset
  } catch {
    throw new Error('invalid cursor')
  }
}

class EventPager {
  constructor(store) {
    this.store = store
  }

  page({ limit, cursor = null }) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
      throw new Error('limit must be between 1 and 100')
    }

    // An offset shifts when a newer event is inserted. Timestamp-only sorting
    // is also ambiguous when multiple events share one timestamp.
    const ordered = this.store
      .all()
      .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
    const offset = cursor ? decodeOffset(cursor) : 0
    const window = ordered.slice(offset, offset + limit)
    const nextOffset = offset + window.length
    return {
      items: window.map((event) => event.serialize()),
      nextCursor: nextOffset < ordered.length ? encodeOffset(nextOffset) : null,
    }
  }
}

module.exports = { Event, EventPager, EventStore }
