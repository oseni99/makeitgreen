'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { Event, EventPager, EventStore } = require('../src/pagination')

const BASE = Date.parse('2026-08-30T12:00:00.000Z')

function event(number, at = new Date(BASE + number * 60_000)) {
  return new Event({ id: `evt-${number}`, createdAt: at, message: `event ${number}` })
}

function ids(page) {
  return page.items.map((item) => item.id)
}

test('returns the public shape with an opaque cursor', () => {
  const page = new EventPager(new EventStore([event(1), event(2), event(3)])).page({ limit: 2 })
  assert.deepEqual(ids(page), ['evt-3', 'evt-2'])
  assert.equal(typeof page.nextCursor, 'string')
  assert.equal(page.nextCursor.includes('evt-2'), false)
  assert.match(page.items[0].createdAt, /Z$/)
})

test('returns no cursor for a terminal page', () => {
  const page = new EventPager(new EventStore([event(1)])).page({ limit: 10 })
  assert.deepEqual(ids(page), ['evt-1'])
  assert.equal(page.nextCursor, null)
})

test('rejects malformed cursors', () => {
  const pager = new EventPager(new EventStore([event(1)]))
  assert.throws(() => pager.page({ limit: 1, cursor: 'not-a-valid-cursor' }), /invalid cursor/)
})

test('uses ID as the deterministic equal-time tie-breaker', () => {
  const at = new Date(BASE)
  const pager = new EventPager(new EventStore([event(2, at), event(3, at), event(1, at)]))
  assert.deepEqual(ids(pager.page({ limit: 10 })), ['evt-3', 'evt-2', 'evt-1'])
})

test('new head inserts do not shift the remaining traversal', () => {
  const store = new EventStore([1, 2, 3, 4, 5].map((number) => event(number)))
  const pager = new EventPager(store)
  const first = pager.page({ limit: 2 })
  assert.deepEqual(ids(first), ['evt-5', 'evt-4'])

  store.add(event(6))
  const second = pager.page({ limit: 2, cursor: first.nextCursor })
  const third = pager.page({ limit: 2, cursor: second.nextCursor })
  assert.deepEqual(ids(second), ['evt-3', 'evt-2'])
  assert.deepEqual(ids(third), ['evt-1'])
  assert.equal(third.nextCursor, null)
})
