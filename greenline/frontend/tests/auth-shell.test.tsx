import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

const { authState } = vi.hoisted(() => ({
  authState: { isLoaded: true, isSignedIn: false },
}))

vi.mock('@clerk/react', () => ({
  SignIn: () => <div>Clerk sign in</div>,
  UserButton: () => <span>User account</span>,
  useAuth: () => authState,
}))

import App from '../src/App'
import { SignInPage } from '../src/auth'

afterEach(() => {
  authState.isLoaded = true
  authState.isSignedIn = false
  vi.unstubAllEnvs()
})

it('shows the sign-in action when Clerk is configured', () => {
  vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', 'pk_test_example')
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <App />,
        children: [{ index: true, element: <main>Home</main> }],
      },
    ],
    { initialEntries: ['/'] },
  )

  render(<RouterProvider router={router} />)

  expect(screen.getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/sign-in')
})

it('presents Clerk inside the branded sign-in page', () => {
  vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', 'pk_test_example')
  render(<SignInPage />)

  expect(screen.getByRole('heading', { name: 'Get back to making it green.' })).toBeTruthy()
  expect(screen.getByRole('region', { name: 'Sign in to MakeItGreen' })).toBeTruthy()
  expect(screen.getByText('Clerk sign in')).toBeTruthy()
})

it('redirects signed-in users away from the sign-in page', async () => {
  vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', 'pk_test_example')
  authState.isSignedIn = true
  const router = createMemoryRouter(
    [
      { path: '/sign-in/*', element: <SignInPage /> },
      { path: '/challenges', element: <main>Challenge catalog</main> },
    ],
    { initialEntries: ['/sign-in'] },
  )

  render(<RouterProvider router={router} />)

  expect(await screen.findByText('Challenge catalog')).toBeTruthy()
})
