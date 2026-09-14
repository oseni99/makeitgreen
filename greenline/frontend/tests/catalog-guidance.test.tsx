import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import Catalog from '../src/pages/Catalog'

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

it('guides a selected prep path toward an attempted challenge', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const method = init?.method ?? 'GET'
      if (url === '/api/me/preferences' && method === 'GET') {
        return json({ prep_path: null })
      }
      if (url === '/api/me/preferences' && method === 'PUT') {
        return json({ prep_path: JSON.parse(String(init?.body)).prep_path })
      }
      if (url === '/api/me/visits' && method === 'POST') {
        return json({ ok: true })
      }
      return json({
        challenges: [
          {
            slug: 'orders-service',
            concept_slug: 'orders-service',
            variant: 'python',
            title: 'Orders service',
            type: 'Concurrency',
            difficulty: 'Medium',
            minutes: 25,
            language: 'Python',
            blurb: 'Repair the checkout race.',
            brief: 'Make checkout atomic.',
            progress: { status: 'attempted', attempts: 1 },
            variants: [
              {
                id: 'python',
                language: 'Python',
                slug: 'orders-service',
                progress: { status: 'todo', attempts: 0 },
              },
              {
                id: 'javascript',
                language: 'JavaScript',
                slug: 'orders-service@javascript',
                progress: { status: 'attempted', attempts: 1 },
              },
            ],
          },
          {
            slug: 'transfer-deadlock',
            concept_slug: 'transfer-deadlock',
            variant: 'python',
            title: 'Transfer deadlock',
            type: 'Concurrency',
            difficulty: 'Medium',
            minutes: 30,
            language: 'Python',
            blurb: 'Establish a global lock order.',
            brief: 'Remove the deadlock.',
            progress: { status: 'todo', attempts: 0 },
            variants: [
              {
                id: 'python',
                language: 'Python',
                slug: 'transfer-deadlock',
                progress: { status: 'todo', attempts: 0 },
              },
              {
                id: 'javascript',
                language: 'JavaScript',
                slug: 'transfer-deadlock@javascript',
                progress: { status: 'todo', attempts: 0 },
              },
            ],
          },
        ],
      })
    }),
  )

  const user = userEvent.setup()
  render(
    <MemoryRouter>
      <Catalog />
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('radio', { name: /Distributed correctness/i }))

  const recommendation = screen.getByRole('link', { name: 'Continue: Orders service' })
  expect(recommendation.getAttribute('href')).toBe('/c/orders-service')
  expect(screen.getByRole('link', { name: 'Orders service' }).getAttribute('href')).toBe('/c/orders-service')
  expect(screen.queryByRole('link', { name: /Orders service: Python/ })).toBeNull()
  expect(screen.queryByRole('link', { name: /Orders service: JavaScript/ })).toBeNull()
  expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
  expect(screen.getAllByText('JavaScript').length).toBeGreaterThan(0)
  expect(screen.getByText('0 of 2 completed')).toBeTruthy()
  expect(localStorage.getItem('greenline-prep-focus')).toBe('distributed')
  expect(screen.getByText('Selected')).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Browse all challenges' })).toBeTruthy()
})
