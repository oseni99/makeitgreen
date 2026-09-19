'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { authorize } = require('../src/authorizer')
const { Unauthorized } = require('../src/errors')

test('authenticates an exact token', () => {
  assert.equal(authorize('tok-alice'), 'alice')
})

test('rejects a lookalike token', () => {
  assert.throws(() => authorize('tok-ali'), Unauthorized)
})

test('requires an exact capability', () => {
  assert.equal(authorize('tok-alice', 'reports:read'), 'alice')
  assert.throws(() => authorize('tok-alice', 'reports:rea'), Unauthorized)
})

test('does not grant capabilities belonging to another user', () => {
  assert.throws(() => authorize('tok-bob', 'reports:write'), Unauthorized)
})

for (const lookalike of ['', 'tok', 'alice', 'ok-alice', 'tok-a']) {
  test(`rejects token fragment ${JSON.stringify(lookalike)}`, () => {
    assert.throws(() => authorize(lookalike), Unauthorized)
  })
}

for (const lookalikeScope of [
  'reports',
  'read',
  'write',
  'reports:',
  'eports:read',
  'ports:write',
]) {
  test(`rejects scope fragment ${lookalikeScope}`, () => {
    assert.throws(() => authorize('tok-alice', lookalikeScope), Unauthorized)
  })
}
