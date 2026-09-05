'use strict'

const { Unauthorized } = require('./errors')

const TOKENS = {
  alice: { token: 'tok-alice', scopes: new Set(['reports:read', 'reports:write']) },
  bob: { token: 'tok-bob', scopes: new Set(['reports:read']) },
}

function authorize(token, requiredScope = null) {
  for (const [user, record] of Object.entries(TOKENS)) {
    if (record.token === token) {
      if (requiredScope !== null && !record.scopes.has(requiredScope)) {
        throw new Unauthorized('scope denied')
      }
      return user
    }
  }
  throw new Unauthorized('invalid token')
}

module.exports = { authorize }
