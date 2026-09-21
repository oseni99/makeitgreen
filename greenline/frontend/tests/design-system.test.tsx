import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

import App from '../src/App'
import { LoadError } from '../src/components/LoadError'
import { PageLoading } from '../src/components/PageLoading'
import { defineGreenlineTheme } from '../src/monacoTheme'
import '../src/styles/tokens.css'

it('opens and closes the primary navigation through its accessible mobile control', async () => {
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
  const user = userEvent.setup()
  render(<RouterProvider router={router} />)

  const openButton = screen.getByRole('button', { name: 'Open navigation menu' })
  expect(openButton.getAttribute('aria-expanded')).toBe('false')
  expect(document.getElementById('mobile-primary-navigation')).toBeNull()

  await user.click(openButton)

  const closeButton = screen.getByRole('button', { name: 'Close navigation menu' })
  expect(closeButton.getAttribute('aria-expanded')).toBe('true')
  expect(document.getElementById('mobile-primary-navigation')).toBeTruthy()

  await user.click(closeButton)

  expect(
    screen.getByRole('button', { name: 'Open navigation menu' }).getAttribute('aria-expanded'),
  ).toBe('false')
  expect(document.getElementById('mobile-primary-navigation')).toBeNull()
})

it('supplies the documented semantic colors to the rendered application theme', () => {
  const styles = getComputedStyle(document.documentElement)

  expect(styles.getPropertyValue('--destructive').trim()).toBe('#c9362b')
  expect(styles.getPropertyValue('--success').trim()).toBe('#16833d')
  expect(styles.getPropertyValue('--warning').trim()).toBe('#a95c00')
})

it('defines Monaco colors from the active application theme', () => {
  const defineTheme = vi.fn()

  defineGreenlineTheme({ editor: { defineTheme } } as never)

  expect(defineTheme).toHaveBeenCalledWith(
    'greenline',
    expect.objectContaining({
      base: 'vs-dark',
      colors: expect.objectContaining({
        'editor.background': '#0a0e0c',
        'editor.foreground': '#d9e8dd',
        'editor.selectionBackground': '#27754a55',
      }),
      rules: expect.arrayContaining([
        expect.objectContaining({ token: 'comment', foreground: '55675e' }),
        expect.objectContaining({ token: 'string', foreground: '77f5a8' }),
        expect.objectContaining({ token: 'keyword', foreground: 'ffb454' }),
        expect.objectContaining({ token: 'number', foreground: 'a8e6c2' }),
      ]),
    }),
  )
})

it('presents load failures as a product recovery state without development instructions', async () => {
  const retry = vi.fn()
  const user = userEvent.setup()

  render(<LoadError onRetry={retry} />)

  expect(screen.getByRole('heading', { name: 'We couldn’t load this page.' })).toBeTruthy()
  expect(screen.queryByText(/uvicorn|:8000/i)).toBeNull()

  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(retry).toHaveBeenCalledOnce()
})

it('uses one accessible full-page loading treatment', () => {
  render(<PageLoading label="Loading challenges…" />)

  expect(screen.getByRole('status').textContent).toContain('Loading challenges…')
})
