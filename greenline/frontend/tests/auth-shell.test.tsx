import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

vi.mock('@clerk/react', () => ({
  SignInButton: ({ children }: { children: React.ReactNode }) => children,
  UserButton: () => <span>User account</span>,
  useAuth: () => ({ isLoaded: true, isSignedIn: false }),
}))

import App from '../src/App'

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

  expect(screen.getByRole('button', { name: 'Sign in with Google' })).toBeTruthy()
})
