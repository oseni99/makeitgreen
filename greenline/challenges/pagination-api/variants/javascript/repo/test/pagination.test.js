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

for (const inputOrder of [
  [2, 3, 1],
  [1, 2, 3],
  [4, 1, 3, 2],
  [2, 4, 1, 3],
  [1, 5, 2, 4, 3],
  [3, 1, 5, 2, 4],
]) {
  test(`uses ID as the equal-time tie-breaker for ${inputOrder.join('-')}`, () => {
    const at = new Date(BASE)
    const pager = new EventPager(
      new EventStore(inputOrder.map((number) => event(number, at))),
    )
    const expected = [...inputOrder]
      .sort((left, right) => right - left)
      .map((number) => `evt-${number}`)
    assert.deepEqual(ids(pager.page({ limit: 10 })), expected)
  })
}

for (const [total, limit] of [[5, 1], [5, 2], [7, 2], [7, 3], [9, 3], [10, 4]]) {
  test(`new head inserts preserve traversal with ${total} events and pages of ${limit}`, () => {
    const store = new EventStore(
      Array.from({ length: total }, (_, index) => event(index + 1)),
    )
    const pager = new EventPager(store)
    const first = pager.page({ limit })
    const seen = ids(first)

    store.add(event(total + 1))
    let cursor = first.nextCursor
    while (cursor !== null) {
      const page = pager.page({ limit, cursor })
      seen.push(...ids(page))
      cursor = page.nextCursor
    }

    const expected = Array.from({ length: total }, (_, index) => `evt-${total - index}`)
    assert.deepEqual(seen, expected)
  })
}
