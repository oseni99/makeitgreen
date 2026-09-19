import { useEffect, useRef } from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceRoute } from '../src/pages/KeyedRoutes'
import { formatRunFailureOutput } from '../src/runFailure'
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

function installServer({
  failSecondFile = false,
  includeNewFile = false,
  includeVariants = false,
  runResult = {},
  streamBeforeComplete = false,
  historyRuns = [],
}: {
  failSecondFile?: boolean
  includeNewFile?: boolean
  includeVariants?: boolean
  runResult?: Record<string, unknown>
  streamBeforeComplete?: boolean
  historyRuns?: Array<Record<string, unknown>>
} = {}) {
  const saves: Array<{
    url: string
    content: string
    response: ReturnType<typeof deferred<Response>>
  }> = []
  let runNumber = 0
  let jobPolls = 0
  let source = 'original source'

  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const method = init?.method ?? 'GET'
    if (url.endsWith('/runs') && method === 'GET') return json({ runs: historyRuns })
    if (url.endsWith('/runs') && method === 'POST') {
      runNumber += 1
      return json({ job_id: `job-${runNumber}`, slug: 'orders-service', status: 'queued' })
    }
    if (url.startsWith('/api/run-jobs/')) {
      if (streamBeforeComplete && jobPolls++ === 0) {
        return json({
          job_id: `job-${runNumber}`,
          slug: 'orders-service',
          status: 'running',
          output: 'partial streamed output',
          next_offset: 23,
        })
      }
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
          ...runResult,
        },
      })
    }
    const restoreMatch = url.match(/\/runs\/(\d+)\/restore$/)
    if (restoreMatch && method === 'POST') {
      const run = historyRuns.find((item) => item.id === Number(restoreMatch[1]))
      const workspace = run?.workspace as Record<string, string> | undefined
      source = workspace?.['orders/service.py'] ?? 'original source'
      return json({ ok: true, run_id: Number(restoreMatch[1]), files_restored: Object.keys(workspace ?? {}).length })
    }
    if (url.endsWith('/files/orders/service.py') && method === 'GET') {
      return json({ content: source })
    }
    if (url.endsWith('/files/orders/other.py') && method === 'GET') {
      return failSecondFile
        ? json({ detail: 'temporary failure' }, 503)
        : json({ content: 'other source' })
    }
    if (url.endsWith('/files/orders/new.py') && method === 'GET') {
      return json({ content: 'new source' })
    }
    if (url.endsWith('/files/orders/new.py') && method === 'DELETE') {
      return json({ ok: true })
    }
    if (url.includes('/files/') && method === 'PUT') {
      const response = deferred<Response>()
      const content = JSON.parse(String(init?.body)).content
      const resolve = response.resolve
      response.resolve = (value) => {
        source = content
        resolve(value)
      }
      saves.push({
        url,
        content,
        response,
      })
      return response.promise
    }
    if (
      (url === '/api/challenges/orders-service' ||
        (includeVariants && url === '/api/challenges/orders-service@javascript')) &&
      method === 'GET'
    ) {
      const javascript = url.endsWith('@javascript')
      return json({
        slug: javascript ? 'orders-service@javascript' : 'orders-service',
        title: 'orders-service',
        type: 'Concurrency',
        difficulty: 'Medium',
        minutes: 25,
        language: javascript ? 'JavaScript' : 'Python',
        blurb: 'Repair the race.',
        brief: 'Make checkout atomic.',
        progress: { status: 'todo', attempts: 0, spoiled: false },
        ...(includeVariants
          ? {
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
                  progress: { status: 'todo', attempts: 0 },
                },
              ],
            }
          : {}),
        files: [
          { path: 'orders/service.py', readonly: false, edited: false },
          { path: 'orders/other.py', readonly: false, edited: false },
          ...(includeNewFile ? [{ path: 'orders/new.py', readonly: false, edited: false, new: true }] : []),
        ],
      })
    }
    throw new Error(`Unhandled request: ${method} ${url}`)
  })

  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, saves }
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
  it('replaces the current history entry when switching challenge languages', async () => {
    installServer({ includeVariants: true })
    const user = userEvent.setup()
    const router = createMemoryRouter(
      [
        { path: '/challenges', element: <div>Challenge catalog</div> },
        { path: '/c/:slug', element: <WorkspaceRoute /> },
      ],
      {
        initialEntries: ['/challenges', '/c/orders-service'],
        initialIndex: 1,
      },
    )
    render(<RouterProvider router={router} />)

    await screen.findByDisplayValue('original source')
    await user.click(screen.getByRole('button', { name: 'JavaScript' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/c/orders-service@javascript'))

    await act(async () => router.navigate(-1))

    expect(await screen.findByText('Challenge catalog')).toBeTruthy()
    expect(router.state.location.pathname).toBe('/challenges')
  })

  it('keeps workspace navigation focused on the brief and files', async () => {
    installServer()
    renderWorkspace()

    await screen.findByDisplayValue('original source')
    const workspacePanel = screen.getByRole('group', { name: 'Workspace panel' })
    expect(within(workspacePanel).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Brief',
      'Files',
    ])
    expect(screen.queryByRole('button', { name: 'Search' })).toBeNull()
  })

  it('preserves streamed output and gives hosted recovery guidance', () => {
    const output = formatRunFailureOutput(
      'challenge execution failed',
      'collecting tests...\n5 passed, 13 failed',
      true,
    )

    expect(output).toContain('collecting tests...')
    expect(output).toContain('challenge execution failed')
    expect(output).toContain('Your code is saved')
    expect(output).not.toContain('localhost')
    expect(output).not.toContain('127.0.0.1')
  })

  it('binds the proxied development server only to IPv4 loopback', () => {
    expect(typeof viteConfig).toBe('object')
    expect(viteConfig.server?.host).toBe('127.0.0.1')
  })

  it('labels a collection failure as an error instead of a zero-test result', async () => {
    installServer({
      runResult: {
        output: 'ERROR collecting tests/test_wallet.py\n1 error during collection',
        passed: 0,
        failed: 0,
        errors: 1,
      },
    })
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await user.click(screen.getByRole('button', { name: /run tests/i }))

    expect(await screen.findByText('1 error')).toBeTruthy()
    expect(screen.queryByText('0 failed · 0 passed')).toBeNull()
  })

  it('shows a first-test target followed by the authentic pytest output', async () => {
    installServer({
      runResult: {
        output: [
          '=================================== FAILURES ===================================',
          '______________________ test_minimum_fee_is_one_cent ______________________',
          '>       assert fee == 1',
          'E       assert 0 == 1',
          'tests/test_wallet.py:41: AssertionError',
        ].join('\n'),
        passed: 3,
        failed: 1,
        tests: [
          {
            id: 'tests/test_wallet.py::test_minimum_fee_is_one_cent',
            outcome: 'failed',
            duration_ms: 0.2,
            file: 'tests/test_wallet.py',
            line: 39,
            message: 'AssertionError: expected minimum fee of 1 cent, got 0',
            crash_file: 'tests/test_wallet.py',
            crash_line: 41,
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await user.click(screen.getByRole('button', { name: /run tests/i }))

    expect(await screen.findByText('Start here:')).toBeTruthy()
    expect(screen.getByText('test_minimum_fee_is_one_cent')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'tests/test_wallet.py:41' })).toBeTruthy()
    expect(screen.getByText('Fix this test, then run again.')).toBeTruthy()
    expect(screen.queryByText(/Red is the starting line/)).toBeNull()
    expect(screen.getByText(/assert 0 == 1/)).toBeTruthy()
  })

  it('replaces the streamed report so a completed run starts at the top', async () => {
    installServer({
      streamBeforeComplete: true,
      runResult: {
        output: 'failure report',
        passed: 0,
        failed: 1,
        tests: [
          {
            id: 'tests/test_wallet.py::test_minimum_fee_is_one_cent',
            outcome: 'failed',
            duration_ms: 0.2,
            file: 'tests/test_wallet.py',
            line: 39,
            message: 'assert 0 == 1',
            crash_file: 'tests/test_wallet.py',
            crash_line: 41,
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await user.click(screen.getByRole('button', { name: /run tests/i }))
    const streamingReport = await screen.findByLabelText('Test report')
    expect(await screen.findByText(/partial streamed output/)).toBeTruthy()
    streamingReport.scrollTop = 200

    expect(await screen.findByText('Start here:')).toBeTruthy()
    const completedReport = screen.getByLabelText('Test report')
    expect(completedReport).not.toBe(streamingReport)
    expect(completedReport.scrollTop).toBe(0)
  })

  it('lets the learner drag and keyboard-resize the test-results drawer', async () => {
    installServer()
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')
    await user.click(screen.getByRole('button', { name: /run tests/i }))

    const drawer = await screen.findByLabelText('Test output')
    const handle = screen.getByRole('separator', { name: 'Resize test output' })
    Object.defineProperty(handle, 'setPointerCapture', { value: vi.fn() })
    Object.defineProperty(handle, 'releasePointerCapture', { value: vi.fn() })
    vi.spyOn(drawer.parentElement!, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      right: 1000,
      bottom: 500,
      left: 0,
      width: 1000,
      height: 500,
      toJSON: () => ({}),
    })

    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 300 })
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 200 })
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 200 })

    expect(drawer.style.height).toBe('60%')
    expect(handle.getAttribute('aria-valuenow')).toBe('60')

    handle.focus()
    await user.keyboard('{ArrowDown}')
    expect(drawer.style.height).toBe('55%')

    await user.click(screen.getByRole('button', { name: /history/i }))
    expect(screen.getByRole('separator', { name: 'Resize test output' })).toBeTruthy()
  })

  it('restores the exact code snapshot from a selected run', async () => {
    const checkpoint = {
      id: 7,
      slug: 'orders-service',
      started_at: '2026-09-07T12:00:00Z',
      duration_ms: 20,
      session_elapsed_ms: 1000,
      green: false,
      passed: 7,
      failed: 10,
      errors: 0,
      skipped: 0,
      exit_code: 1,
      output_tail: '7 passed, 10 failed',
      output_truncated: false,
      tests: [],
      snapshot_available: true,
      workspace: { 'orders/service.py': 'checkpoint source' },
    }
    const { fetchMock } = installServer({ historyRuns: [checkpoint] })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')
    await replaceEditorText(user, 'worse source')

    await user.click(screen.getByRole('button', { name: /history/i }))
    await user.click(await screen.findByRole('button', { name: 'Restore code from run 7' }))

    expect(confirm).toHaveBeenCalledWith(
      'Restore code from run 7? Your current workspace files will be replaced.',
    )
    expect(await screen.findByDisplayValue('checkpoint source')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/challenges/orders-service/runs/7/restore',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(await screen.findByText(/7 passed, 10 failed/)).toBeTruthy()
    confirm.mockRestore()
  })

  it('waits for an in-flight save before restoring a run checkpoint', async () => {
    const checkpoint = {
      id: 7,
      slug: 'orders-service',
      started_at: '2026-09-07T12:00:00Z',
      duration_ms: 20,
      session_elapsed_ms: 1000,
      green: false,
      passed: 7,
      failed: 10,
      errors: 0,
      skipped: 0,
      exit_code: 1,
      output_tail: '7 passed, 10 failed',
      output_truncated: false,
      tests: [],
      snapshot_available: true,
      workspace: { 'orders/service.py': 'checkpoint source' },
    }
    const { fetchMock, saves } = installServer({ historyRuns: [checkpoint] })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')
    await replaceEditorText(user, 'unsaved source')

    await editorHarness.save?.()
    await waitFor(() => expect(saves).toHaveLength(1))
    await user.click(screen.getByRole('button', { name: /history/i }))
    await user.click(await screen.findByRole('button', { name: 'Restore code from run 7' }))

    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/challenges/orders-service/runs/7/restore',
      expect.anything(),
    )

    saves[0].response.resolve(json({ ok: true }))

    expect(await screen.findByDisplayValue('checkpoint source')).toBeTruthy()
    const restoredRead = await fetch('/api/challenges/orders-service/files/orders/service.py')
    expect(await restoredRead.json()).toEqual({ content: 'checkpoint source' })
  })

  it('shows at most the latest ten run checkpoints', async () => {
    const historyRuns = Array.from({ length: 12 }, (_, index) => ({
      id: 12 - index,
      slug: 'orders-service',
      started_at: '2026-09-07T12:00:00Z',
      duration_ms: 20,
      session_elapsed_ms: 1000,
      green: false,
      passed: index,
      failed: 17 - index,
      errors: 0,
      skipped: 0,
      exit_code: 1,
      output_tail: 'failed',
      output_truncated: false,
      tests: [],
      snapshot_available: true,
      workspace: { 'orders/service.py': `checkpoint ${12 - index}` },
    }))
    installServer({ historyRuns })
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await user.click(screen.getByRole('button', { name: /history/i }))

    expect(await screen.findByRole('button', { name: /history \(10\)/i })).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /Restore code from run/ })).toHaveLength(10)
    expect(screen.queryByRole('button', { name: 'Restore code from run 2' })).toBeNull()
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

  it('protects unsaved edits when deleting a created file is canceled', async () => {
    const { fetchMock } = installServer({ includeNewFile: true })
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWorkspace()
    await screen.findByDisplayValue('original source')

    await user.click(screen.getByRole('button', { name: 'Files' }))
    await user.click(screen.getByRole('button', { name: /^orders\/new\.py/ }))
    await replaceEditorText(user, 'important unsaved work')
    await user.click(screen.getByRole('button', { name: 'delete orders/new.py' }))

    expect(confirm).toHaveBeenCalledWith('You have unsaved changes. Delete this file anyway?')
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/challenges/orders-service/files/orders/new.py',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect((screen.getByRole('textbox', { name: 'code editor' }) as HTMLTextAreaElement).value).toBe('important unsaved work')
    expect(screen.getByTitle('orders/new.py').textContent).toContain('•')
    confirm.mockRestore()
  })

  it('waits for the learner to choose and start a timer', async () => {
    const { fetchMock } = installServer()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByDisplayValue('original source')
    const idleTimer = screen.getByTitle('set timer')
    expect(idleTimer.textContent).toBe('⏱ Set timer')
    expect(idleTimer.className).toContain('rounded-md')

    await user.click(idleTimer)
    const controls = screen.getByRole('dialog', { name: 'Timer controls' })
    expect(within(controls).getByText('~25 min suggested')).toBeTruthy()
    await user.click(
      within(controls).getByRole('button', { name: 'Start 15 minute timer' }),
    )

    expect(screen.getByTitle('time remaining').textContent).toMatch(/^⏱ 1[45]:\d{2}$/)
    expect(screen.getByTitle('time remaining').className).toContain('rounded-full')
    await user.click(screen.getByTitle('time remaining'))
    expect(screen.getByTitle('timer paused').textContent).toContain('paused')
    expect(screen.queryByRole('dialog', { name: 'Timer controls' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Reset timer' })).toBeTruthy()

    await user.click(screen.getByTitle('timer paused'))
    expect(screen.getByTitle('time remaining')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reset timer' })).toBeNull()
    await user.click(screen.getByTitle('time remaining'))

    const stored = JSON.parse(localStorage.getItem('greenline-timer-orders-service') ?? '{}')
    expect(stored.status).toBe('paused')
    expect(stored.durationMinutes).toBe(15)

    await user.click(screen.getByRole('button', { name: /run tests/i }))
    await waitFor(() => {
      const runRequest = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/runs') && init?.method === 'POST',
      )
      expect(JSON.parse(String(runRequest?.[1]?.body)).session_elapsed_ms).toBeGreaterThanOrEqual(0)
    })

    await user.click(screen.getByRole('button', { name: 'Reset timer' }))
    expect(screen.getByTitle('set timer').textContent).toBe('⏱ Set timer')
  })

  it('does not report session time when the learner leaves the timer idle', async () => {
    const { fetchMock } = installServer()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByDisplayValue('original source')
    await user.click(screen.getByRole('button', { name: /run tests/i }))

    await waitFor(() => {
      const runRequest = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/runs') && init?.method === 'POST',
      )
      expect(JSON.parse(String(runRequest?.[1]?.body)).session_elapsed_ms).toBeNull()
    })
  })

  it('recovers from structurally invalid timer JSON as an idle timer', async () => {
    installServer()
    localStorage.setItem('greenline-timer-orders-service', '{}')
    renderWorkspace()

    await screen.findByDisplayValue('original source')
    const timer = screen.getByTitle('set timer')
    expect(timer.textContent).not.toContain('NaN')
    expect(timer.textContent).toBe('⏱ Set timer')
  })

  it('still opens the workspace when persisting recovered timer state fails', async () => {
    installServer()
    localStorage.setItem('greenline-timer-orders-service', 'null')
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('storage disabled', 'SecurityError')
    })

    renderWorkspace()

    expect(await screen.findByDisplayValue('original source')).toBeTruthy()
    expect((await screen.findByTitle('set timer')).textContent).toBe('⏱ Set timer')
    setItem.mockRestore()
  })
})
