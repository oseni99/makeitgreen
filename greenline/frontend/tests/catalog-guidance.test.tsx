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
})

it('guides a selected prep path toward an attempted challenge', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      json({
        challenges: [
          {
            slug: 'orders-service',
            title: 'Orders service',
            type: 'Concurrency',
            difficulty: 'Medium',
            minutes: 25,
            language: 'Python',
            blurb: 'Repair the checkout race.',
            brief: 'Make checkout atomic.',
            progress: { status: 'attempted', attempts: 1 },
          },
          {
            slug: 'transfer-deadlock',
            title: 'Transfer deadlock',
            type: 'Concurrency',
            difficulty: 'Medium',
            minutes: 30,
            language: 'Python',
            blurb: 'Establish a global lock order.',
            brief: 'Remove the deadlock.',
            progress: { status: 'todo', attempts: 0 },
          },
        ],
      }),
    ),
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
  expect(screen.getByText('0 of 2 completed')).toBeTruthy()
  expect(localStorage.getItem('greenline-prep-focus')).toBe('distributed')
  expect(screen.getByText('Selected')).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Browse all challenges' })).toBeTruthy()
})
