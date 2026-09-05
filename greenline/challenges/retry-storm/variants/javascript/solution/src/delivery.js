'use strict'

class DeliveryRejected extends Error {}
class RetryExhausted extends Error {}

function deliver(send, sleep, { maxAttempts = 3, baseDelay = 1, maxDelay = 8 } = {}) {
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
    throw new Error('maxAttempts must be positive')
  }
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const response = send()
    if (response.status >= 200 && response.status < 300) return response
    if (response.status !== 429 && response.status !== 503) {
      throw new DeliveryRejected(`permanent response ${response.status}`)
    }
    if (attempt === maxAttempts - 1) break

    const retryAfter = response.headers['Retry-After'] ?? ''
    const delay = /^\d+$/.test(retryAfter)
      ? Number(retryAfter)
      : Math.min(baseDelay * (2 ** attempt), maxDelay)
    sleep(delay)
  }
  throw new RetryExhausted('delivery attempts exhausted')
}

module.exports = { DeliveryRejected, RetryExhausted, deliver }
