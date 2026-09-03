import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

beforeEach(() => {
  vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', undefined)
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  vi.unstubAllEnvs()
})
