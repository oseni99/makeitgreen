'use strict'

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function clone(value) {
  if (Array.isArray(value)) return value.map(clone)
  if (isPlainObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, clone(item)]))
  }
  return value
}

function mergeConfig(defaults, overrides) {
  const result = clone(defaults)
  for (const [key, value] of Object.entries(overrides)) {
    if (isPlainObject(value) && isPlainObject(result[key])) {
      result[key] = mergeConfig(result[key], value)
    } else if (value) {
      result[key] = clone(value)
    }
  }
  return result
}

module.exports = { mergeConfig }
