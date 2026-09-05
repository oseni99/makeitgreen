'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { DeliveryRejected, RetryExhausted, deliver } = require('../src/delivery')

function sender(responses) {
  let calls = 0
  return {
    send() {
      const response = responses[calls]
      calls += 1
      return response
    },
    get calls() { return calls },
  }
}

test('success does not retry or sleep', () => {
  const transport = sender([{ status: 204, headers: {} }])
  const sleeps = []
  assert.equal(deliver(transport.send, (delay) => sleeps.push(delay)).status, 204)
  assert.equal(transport.calls, 1)
  assert.deepEqual(sleeps, [])
})

test('transient failures back off and then succeed', () => {
  const transport = sender([
    { status: 503, headers: {} },
    { status: 503, headers: {} },
    { status: 200, headers: {} },
  ])
  const sleeps = []
  assert.equal(deliver(transport.send, (delay) => sleeps.push(delay), { baseDelay: 0.5 }).status, 200)
  assert.deepEqual(sleeps, [0.5, 1])
})

test('Retry-After overrides client backoff', () => {
  const transport = sender([
    { status: 429, headers: { 'Retry-After': '7' } },
    { status: 200, headers: {} },
  ])
  const sleeps = []
  deliver(transport.send, (delay) => sleeps.push(delay))
  assert.deepEqual(sleeps, [7])
})

for (const status of [400, 401, 404, 500]) {
  test(`status ${status} is a permanent rejection`, () => {
    const transport = sender([{ status, headers: {} }, { status: 200, headers: {} }])
    assert.throws(() => deliver(transport.send, () => {}), DeliveryRejected)
    assert.equal(transport.calls, 1)
  })
}

test('attempt budget has no extra call or sleep', () => {
  const transport = sender([
    { status: 503, headers: {} },
    { status: 503, headers: {} },
    { status: 200, headers: {} },
  ])
  const sleeps = []
  assert.throws(
    () => deliver(transport.send, (delay) => sleeps.push(delay), { maxAttempts: 2, baseDelay: 5 }),
    RetryExhausted,
  )
  assert.equal(transport.calls, 2)
  assert.deepEqual(sleeps, [5])
})

test('caps exponential delay', () => {
  const transport = sender(Array.from({ length: 5 }, () => ({ status: 503, headers: {} })))
  const sleeps = []
  assert.throws(
    () => deliver(transport.send, (delay) => sleeps.push(delay), { maxAttempts: 5, baseDelay: 3, maxDelay: 5 }),
    RetryExhausted,
  )
  assert.deepEqual(sleeps, [3, 5, 5, 5])
})
