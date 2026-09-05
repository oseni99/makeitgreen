import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

const { signOut } = vi.hoisted(() => ({ signOut: vi.fn(async () => {}) }))

vi.mock('@clerk/react', () => ({
  useClerk: () => ({ signOut }),
  useUser: () => ({
    isLoaded: true,
    isSignedIn: true,
    user: {
      fullName: 'Oluwatosin Oseni',
      firstName: 'Oluwatosin',
      imageUrl: '/avatar.png',
      primaryEmailAddress: { emailAddress: 'kingosenitosin@gmail.com' },
    },
  }),
}))

import { ProfileLink } from '../src/components/ProfileLink'
import Profile from '../src/pages/Profile'

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  signOut.mockClear()
})

it('opens the product profile directly without another menu', () => {
  render(
    <MemoryRouter>
      <ProfileLink />
    </MemoryRouter>,
  )

  expect(screen.getByRole('link', { name: 'Open profile' }).getAttribute('href')).toBe('/profile')
})

it('shows learner identity, progress, prep path, and the next challenge', async () => {
  const user = userEvent.setup()
  vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', 'pk_test_example')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const method = init?.method ?? 'GET'
      if (url === '/api/me/preferences' && method === 'GET') return json({ prep_path: 'distributed' })
      if (url === '/api/me/activity') {
        return json({ solves: [{ slug: 'wallet-service', solved_at: new Date().toISOString() }] })
      }
      if (url === '/api/challenges') {
        return json({
          challenges: [
            {
              slug: 'orders-service',
              title: 'orders-service',
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
              slug: 'wallet-service',
              title: 'wallet-service',
              type: 'Repository Implementation',
              difficulty: 'Easy',
              minutes: 20,
              language: 'Python',
              blurb: 'Repair wallet invariants.',
              brief: 'Keep balances valid.',
              progress: { status: 'solved', attempts: 2 },
            },
          ],
        })
      }
      throw new Error(`Unhandled request: ${url}`)
    }),
  )

  render(
    <MemoryRouter>
      <Profile />
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: 'Oluwatosin Oseni' })).toBeTruthy()
  expect(screen.getByText('Distributed correctness')).toBeTruthy()
  const activity = screen.getByRole('group', { name: 'Daily solve activity' })
  expect(activity.children).toHaveLength(182)
  expect(screen.getByLabelText(/1 challenge solved/)).toBeTruthy()
  expect(screen.getByText('1 solved · 1 in progress · 0 remaining')).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Open challenge' }).getAttribute('href')).toBe(
    '/c/orders-service@javascript',
  )
  await user.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(signOut).toHaveBeenCalledWith({ redirectUrl: '/' })
})
