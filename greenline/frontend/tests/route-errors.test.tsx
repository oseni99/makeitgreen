import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { expect, it } from 'vitest'

import RouteError from '../src/pages/RouteError'
import { appRoutes } from '../src/routes'

it('shows a branded recovery page for an unmatched route', () => {
  const router = createMemoryRouter(appRoutes, { initialEntries: ['/c'] })

  render(<RouterProvider router={router} />)

  expect(screen.getByRole('heading', { name: 'This page does not exist.' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Browse challenges' }).getAttribute('href')).toBe(
    '/challenges',
  )
  expect(screen.queryByText('Unexpected Application Error!')).toBeNull()
})

it('hides technical details when an unexpected route error occurs', async () => {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        loader: () => {
          throw new Error('database password and internal stack details')
        },
        element: <main>Should not render</main>,
        errorElement: <RouteError />,
      },
    ],
    { initialEntries: ['/'] },
  )

  render(<RouterProvider router={router} />)

  expect(await screen.findByRole('heading', { name: 'Something went wrong.' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  expect(screen.queryByText(/database password/i)).toBeNull()
  expect(screen.queryByText(/internal stack/i)).toBeNull()
})
