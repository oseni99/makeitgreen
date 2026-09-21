import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { SolutionRoute } from '../src/pages/KeyedRoutes'

vi.mock('../src/monacoSetup', () => ({}))
vi.mock('../src/monacoLanguages', () => ({
  useMonacoLanguage: (language: string) => language,
}))

vi.mock('@monaco-editor/react', () => ({
  loader: { config: () => {} },
  DiffEditor: () => null,
}))

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

it('shows an in-product error when a gated solution cannot be unlocked', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const method = init?.method ?? 'GET'

      if (url === '/api/challenges/orders-service' && method === 'GET') {
        return json({
          slug: 'orders-service',
          progress: { status: 'todo', attempts: 0, spoiled: false },
        })
      }
      if (url === '/api/challenges/orders-service/spoil' && method === 'POST') {
        return json({ detail: 'temporary failure' }, 503)
      }
      throw new Error(`Unhandled request: ${method} ${url}`)
    }),
  )

  const router = createMemoryRouter(
    [{ path: '/c/:slug/solution', element: <SolutionRoute /> }],
    { initialEntries: ['/c/orders-service/solution'] },
  )
  const user = userEvent.setup()
  render(<RouterProvider router={router} />)

  await user.click(await screen.findByRole('button', { name: 'Confirm' }))

  expect((await screen.findByRole('alert')).textContent).toBe(
    'Could not unlock the solution. Your progress was not changed. Try again.',
  )
  expect(screen.getByRole('heading', { name: 'orders-service — official fix' })).toBeTruthy()
})
