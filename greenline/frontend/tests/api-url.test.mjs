import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError, api, fileUrl, isNotFoundError } from '../src/api.ts'

test('file URLs preserve reserved characters inside path segments', () => {
  const hashUrl = new URL(fileUrl('demo', 'src/name#part.py'), 'http://greenline.local')
  const queryUrl = new URL(fileUrl('demo', 'src/name?part.py'), 'http://greenline.local')

  assert.equal(hashUrl.pathname, '/api/challenges/demo/files/src/name%23part.py')
  assert.equal(hashUrl.hash, '')
  assert.equal(queryUrl.pathname, '/api/challenges/demo/files/src/name%3Fpart.py')
  assert.equal(queryUrl.search, '')
})

test('file URLs preserve directory separators while encoding each segment', () => {
  assert.equal(
    fileUrl('demo', 'orders/nested module/50%off.py'),
    '/api/challenges/demo/files/orders/nested%20module/50%25off.py',
  )
})

test('API errors retain HTTP status so missing files are distinguishable', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async () => new Response('', { status: 404 })
  await assert.rejects(api.getFile('demo', 'missing.py'), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 404)
    assert.equal(isNotFoundError(error), true)
    return true
  })

  globalThis.fetch = async () => new Response('', { status: 500 })
  await assert.rejects(api.getFile('demo', 'broken.py'), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 500)
    assert.equal(isNotFoundError(error), false)
    return true
  })
})
