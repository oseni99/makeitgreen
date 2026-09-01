import { useEffect, useRef } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceRoute } from '../src/pages/KeyedRoutes'
import viteConfig from '../vite.config'

const editorHarness = vi.hoisted(() => ({
  save: null as null | (() => Promise<void>),
}))

vi.mock('@monaco-editor/react', () => {
  const editor = {
    addCommand: (_key: number, command: () => void) => {
      editorHarness.save = async () => command()
    },
    onDidChangeModel: () => ({ dispose: () => {} }),
    getModel: () => null,
  }
  const monaco = {
    KeyMod: { CtrlCmd: 1 },
    KeyCode: { KeyS: 2 },
    MarkerSeverity: { Error: 8 },
    editor: { setModelMarkers: () => {} },
  }

  function MockEditor({
    value,
    onChange,
    onMount,
  }: {
    value: string
    onChange?: (value: string) => void
    onMount?: (editor: typeof editor, monaco: typeof monaco) => void
  }) {
    const mounted = useRef(false)
    useEffect(() => {
      if (mounted.current) return
      mounted.current = true
      onMount?.(editor, monaco)
    }, [onMount])
    return (
      <textarea
        aria-label="code editor"
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
      />
    )
  }

  return { default: MockEditor, DiffEditor: () => null }
})

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function installServer({ failSecondFile = false } = {}) {
  const saves: Array<{
    url: string
    content: string
    response: ReturnType<typeof deferred<Response>>
  }> = []
  let runNumber = 0

  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const method = init?.method ?? 'GET'
    if (url.endsWith('/runs') && method === 'GET') return json({ runs: [] })
    if (url.endsWith('/runs') && method === 'POST') {
      runNumber += 1
      return json({ job_id: `job-${runNumber}`, slug: 'orders-service', status: 'queued' })
    }
    if (url.startsWith('/api/run-jobs/')) {
      return json({
        job_id: `job-${runNumber}`,
        slug: 'orders-service',
        status: 'completed',
        output: '',
        next_offset: 0,
        result: {
          exit_code: 1,
          green: false,
          output: '1 failed',
          tests: [],
          passed: 0,
          failed: 1,
          errors: 0,
          skipped: 0,
        },
      })
    }
    if (url.endsWith('/files/orders/service.py') && method === 'GET') {
      return json({ content: 'original source' })
    }
    if (url.endsWith('/files/orders/other.py') && method === 'GET') {
      return failSecondFile
        ? json({ detail: 'temporary failure' }, 503)
        : json({ content: 'other source' })
    }
    if (url.includes('/files/') && method === 'PUT') {
      const response = deferred<Response>()
      saves.push({
        url,
        content: JSON.parse(String(init?.body)).content,
        response,
      })
      return response.promise
    }
    if (url === '/api/challenges/orders-service' && method === 'GET') {
      return json({
        slug: 'orders-service',
        title: 'orders-service',
        type: 'Concurrency',
        difficulty: 'Medium',
        minutes: 25,
        language: 'Python',
        blurb: 'Repair the race.',
        brief: 'Make checkout atomic.',
        progress: { status: 'todo', attempts: 0, spoiled: false },
        files: [
          { path: 'orders/service.py', readonly: false, edited: false },
          { path: 'orders/other.py', readonly: false, edited: false },
        ],
      })
    }
    throw new Error(`Unhandled request: ${method} ${url}`)
  })

  vi.stubGlobal('fetch', fetchMock)
  return { saves }
}

function renderWorkspace() {
  const router = createMemoryRouter(
    [{ path: '/c/:slug', element: <WorkspaceRoute /> }],
    { initialEntries: ['/c/orders-service'] },
  )
  render(<RouterProvider router={router} />)
}

async function replaceEditorText(user: ReturnType<typeof userEvent.setup>, value: string) {
  const editor = screen.getByRole('textbox', { name: 'code editor' })
  await user.clear(editor)
  await user.type(editor, value)
}

afterEach(() => {
  editorHarness.save = null
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('workspace reliability', () => {
  it('binds the proxied development server only to IPv4 loopback', () => {
    expect(typeof viteConfig).toBe('object')
    expect(viteConfig.server?.host).toBe('127.0.0.1')
  })

  it('saves an edit made while save-all is in flight on the next run', async () => {
    const { saves } = installServer()
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await replaceEditorText(user, 'first edit')
    await user.click(screen.getByRole('button', { name: /run tests/i }))
    await waitFor(() => expect(saves).toHaveLength(1))
    expect(saves[0].content).toBe('first edit')

    await replaceEditorText(user, 'newer edit')
    saves[0].response.resolve(json({ ok: true }))
    await screen.findByRole('button', { name: /run tests/i })

    await user.click(screen.getByRole('button', { name: /run tests/i }))
    await waitFor(() => expect(saves).toHaveLength(2))
    expect(saves[1].content).toBe('newer edit')
    saves[1].response.resolve(json({ ok: true }))
  })

  it('saves an edit made while save-current is in flight on the next save', async () => {
    const { saves } = installServer()
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await replaceEditorText(user, 'first edit')
    expect(editorHarness.save).not.toBeNull()
    act(() => void editorHarness.save?.())
    await waitFor(() => expect(saves).toHaveLength(1))

    await replaceEditorText(user, 'newer edit')
    await act(async () => {
      saves[0].response.resolve(json({ ok: true }))
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })
    await waitFor(() => expect(screen.getByTitle('orders/service.py').textContent).toContain('•'))

    act(() => void editorHarness.save?.())
    await waitFor(() => expect(saves).toHaveLength(2))
    expect(saves[1].content).toBe('newer edit')
    saves[1].response.resolve(json({ ok: true }))
  })

  it('keeps the current file intact when another file fails to open', async () => {
    const { saves } = installServer({ failSecondFile: true })
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await user.click(screen.getByRole('button', { name: 'Files' }))
    await user.click(screen.getByRole('button', { name: 'orders/other.py' }))

    expect(await screen.findByText('could not open file')).toBeTruthy()
    expect((screen.getByRole('textbox', { name: 'code editor' }) as HTMLTextAreaElement).value)
      .toBe('original source')
    expect(screen.queryByTitle('orders/other.py')).toBeNull()

    await replaceEditorText(user, 'safe edit')
    act(() => void editorHarness.save?.())
    await waitFor(() => expect(saves).toHaveLength(1))
    expect(saves[0].url).toContain('/files/orders/service.py')
    saves[0].response.resolve(json({ ok: true }))
  })
})
