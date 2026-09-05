'use strict'

const assert = require('node:assert/strict')
const test = require('node:test')
const { mergeConfig } = require('../src/merge')

test('merges nested values', () => {
  assert.deepEqual(
    mergeConfig({ db: { host: 'localhost', port: 5432 } }, { db: { host: 'db' } }),
    { db: { host: 'db', port: 5432 } },
  )
})

test('treats false, zero, and empty string as real overrides', () => {
  assert.deepEqual(
    mergeConfig(
      { debug: true, workers: 4, label: 'prod' },
      { debug: false, workers: 0, label: '' },
    ),
    { debug: false, workers: 0, label: '' },
  )
})

test('does not mutate inputs or retain nested references', () => {
  const defaults = { feature: { enabled: true }, hosts: ['a'] }
  const overrides = { feature: { enabled: false }, hosts: ['b'] }
  const merged = mergeConfig(defaults, overrides)
  merged.hosts.push('c')

  assert.deepEqual(defaults, { feature: { enabled: true }, hosts: ['a'] })
  assert.deepEqual(overrides, { feature: { enabled: false }, hosts: ['b'] })
})
