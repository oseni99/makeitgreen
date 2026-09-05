'use strict'

class DeliveryRejected extends Error {}
class RetryExhausted extends Error {}

function deliver(send, sleep, { maxAttempts = 3, baseDelay = 1, maxDelay = 8 } = {}) {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const response = send()
    if (response.status >= 200 && response.status < 300) return response
  }
  throw new RetryExhausted('delivery attempts exhausted')
}

module.exports = { DeliveryRejected, RetryExhausted, deliver }
