import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

vi.mock('@clerk/react', () => ({
  SignIn: () => <div>Clerk sign in</div>,
  UserButton: () => <span>User account</span>,
  useAuth: () => ({ isLoaded: true, isSignedIn: false }),
}))

import App from '../src/App'
import { SignInPage } from '../src/auth'

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
  render(<SignInPage />)

  expect(screen.getByRole('heading', { name: 'Get back to making it green.' })).toBeTruthy()
  expect(screen.getByRole('region', { name: 'Sign in to MakeItGreen' })).toBeTruthy()
  expect(screen.getByText('Clerk sign in')).toBeTruthy()
})
