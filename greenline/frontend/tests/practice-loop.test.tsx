import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from '../src/App'
import Catalog from '../src/pages/Catalog'
import { SolutionRoute, WorkspaceRoute } from '../src/pages/KeyedRoutes'

vi.mock('../src/monacoSetup', () => ({}))
vi.mock('../src/monacoLanguages', () => ({
  useMonacoLanguage: (language: string) => language,
}))

vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }: { value: string; onChange?: (value: string) => void }) => (
    <textarea
      aria-label="code editor"
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
    />
  ),
  DiffEditor: ({ original, modified }: { original: string; modified: string }) => (
    <div aria-label="solution diff">
      <pre>{original}</pre>
      <pre>{modified}</pre>
    </div>
  ),
}))

const challenge = {
  slug: 'orders-service',
  title: 'orders-service',
  type: 'Concurrency',
  difficulty: 'Medium',
  minutes: 25,
  language: 'Python',
  blurb: 'Repair the checkout race.',
  brief: 'Make checkout atomic.',
  progress: { status: 'todo', attempts: 0, spoiled: false },
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installPracticeLoopServer() {
  let source = 'def checkout():\n    return "broken"\n'
  let runNumber = 0
  const runs: unknown[] = []
  const jobs = new Map<string, unknown>()
  let debrief: unknown = null

  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const method = init?.method ?? 'GET'

    if (url === '/api/challenges' && method === 'GET') {
      return json({ challenges: [challenge] })
    }
    if (url === '/api/me/preferences' && method === 'GET') {
      return json({ prep_path: null })
    }
    if (url === '/api/me/visits' && method === 'POST') {
      return json({ ok: true })
    }
    if (url === '/api/challenges/orders-service' && method === 'GET') {
      return json({
        ...challenge,
        progress: {
          ...challenge.progress,
          status: runNumber >= 2 ? 'solved' : runNumber === 1 ? 'attempted' : 'todo',
          attempts: runNumber,
        },
        files: [{ path: 'orders/service.py', readonly: false, edited: runNumber >= 2 }],
      })
    }
    if (url === '/api/challenges/orders-service/files/orders/service.py' && method === 'GET') {
      return json({ content: source })
    }
    if (url === '/api/challenges/orders-service/files/orders/service.py' && method === 'PUT') {
      source = JSON.parse(String(init?.body)).content
      return json({ ok: true })
    }
    if (url === '/api/challenges/orders-service/runs' && method === 'GET') {
      return json({ runs })
    }
    if (url === '/api/challenges/orders-service/runs' && method === 'POST') {
      runNumber += 1
      const green = runNumber >= 2 && source.includes('fixed')
      const run = {
        id: runNumber,
        slug: challenge.slug,
        started_at: '2026-08-31T12:00:00Z',
        duration_ms: 20,
        session_elapsed_ms: 1000,
        green,
        passed: green ? 2 : 1,
        failed: green ? 0 : 1,
        errors: 0,
        skipped: 0,
        exit_code: green ? 0 : 1,
      }
      runs.unshift({ ...run, output_tail: green ? '2 passed' : '1 failed, 1 passed', output_truncated: false, tests: [] })
      const jobId = `job-${runNumber}`
      jobs.set(jobId, { ...run, output: green ? '2 passed' : '1 failed, 1 passed', tests: [], run })
      return json({ job_id: jobId, slug: challenge.slug, status: 'queued' })
    }
    if (url.startsWith('/api/run-jobs/') && method === 'GET') {
      const jobId = url.split('/api/run-jobs/')[1].split('?')[0]
      const result = jobs.get(jobId)
      return json({
        job_id: jobId,
        slug: challenge.slug,
        status: 'completed',
        output: result && typeof result === 'object' && 'output' in result ? result.output : '',
        next_offset: 20,
        result,
      })
    }
    if (url === '/api/challenges/orders-service/solution' && method === 'GET') {
      return json({
        writeup: '# Atomic checkout\n\n## Root cause\n\nThe reservation is not atomic.',
        files: [
          {
            path: 'orders/service.py',
            original: 'def checkout():\n    return "broken"\n',
            content: 'def checkout():\n    return "fixed"\n',
          },
        ],
      })
    }
    if (url === '/api/challenges/orders-service/debrief' && method === 'GET') {
      return json({ debrief })
    }
    if (url === '/api/challenges/orders-service/debrief' && method === 'PUT') {
      debrief = {
        ...JSON.parse(String(init?.body)),
        updated_at: '2026-09-04T12:00:00Z',
      }
      return json({ debrief })
    }
    throw new Error(`Unhandled request: ${method} ${url}`)
  })

  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('practice loop', () => {
  it('moves from catalog through edit and green run to the reference solution', async () => {
    const { fetchMock } = installPracticeLoopServer()
    const user = userEvent.setup()
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <App />,
          children: [
            { path: 'challenges', element: <Catalog /> },
            { path: 'c/:slug', element: <WorkspaceRoute /> },
            { path: 'c/:slug/solution', element: <SolutionRoute /> },
          ],
        },
      ],
      { initialEntries: ['/challenges'] },
    )

    render(<RouterProvider router={router} />)

    expect(await screen.findByRole('heading', { name: 'Challenges' })).toBeTruthy()
    await user.click(screen.getByRole('link', { name: 'orders-service' }))

    const editor = await screen.findByRole('textbox', { name: 'code editor' })
    expect((editor as HTMLTextAreaElement).value).toBe('def checkout():\n    return "broken"\n')
    const challengeDetails = screen.getByRole('group', { name: 'Challenge details' })
    expect(within(challengeDetails).getByText('Concurrency')).toBeTruthy()
    expect(within(challengeDetails).getByText('Medium')).toBeTruthy()
    expect(within(challengeDetails).getByText('○ TODO')).toBeTruthy()
    expect(within(challengeDetails).getByText('~25 min')).toBeTruthy()
    expect(within(challengeDetails).getByText('Python')).toBeTruthy()
    expect(within(challengeDetails).getByText('0 attempts')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: /run tests/i }))
    expect(await screen.findByText('1 failed · 1 passed')).toBeTruthy()
    expect(screen.getByText('◐ ATTEMPTED')).toBeTruthy()

    await user.clear(editor)
    await user.type(editor, 'def checkout():\n    return "fixed"\n')
    await user.click(screen.getByRole('button', { name: /run tests/i }))

    expect(await screen.findByText('All tests green. Nice.')).toBeTruthy()
    expect(screen.getByText('● SOLVED')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/challenges/orders-service/files/orders/service.py',
      expect.objectContaining({ method: 'PUT' }),
    )

    await user.click(screen.getByRole('link', { name: /compare with the reference solution/i }))
    expect(
      await screen.findByRole('heading', { name: 'orders-service — official fix' }),
    ).toBeTruthy()
    expect(await screen.findByText('The reservation is not atomic.')).toBeTruthy()
    expect(screen.queryByText('Atomic checkout')).toBeNull()
    expect(screen.getByRole('heading', { name: 'The fix' })).toBeTruthy()
    expect(screen.getByText('1 file changed')).toBeTruthy()
    expect(screen.getAllByText('+1')).toHaveLength(2)
    expect(screen.getAllByText('−1')).toHaveLength(2)
    expect(screen.getByText('Starter code')).toBeTruthy()
    expect(screen.getByText('Official solution')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'broken' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'fixed' })).toBeNull()
    expect(screen.queryByRole('button', { name: /your work/i })).toBeNull()
    await waitFor(() => expect(screen.getByLabelText('solution diff')).toBeTruthy())

    await user.click(screen.getByRole('button', { name: 'collapse' }))
    expect(screen.queryByLabelText('solution diff')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'expand' }))
    await waitFor(() => expect(screen.getByLabelText('solution diff')).toBeTruthy())

    await user.click(screen.getByRole('button', { name: 'Add reflection' }))
    await user.type(screen.getByLabelText('What was the root cause?'), 'A check-write race.')
    await user.type(screen.getByLabelText('Why does the fix work?'), 'The mutation is atomic.')
    await user.type(
      screen.getByLabelText('What tradeoff did it introduce?'),
      'The critical section is serialized.',
    )
    await user.click(screen.getByRole('button', { name: 'Yes' }))
    await user.type(screen.getByLabelText(/Anything we should improve/), 'Add a retry case.')
    await user.click(screen.getByRole('button', { name: 'Save debrief' }))

    expect(await screen.findByText('Saved')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/challenges/orders-service/debrief',
      expect.objectContaining({ method: 'PUT' }),
    )
  })
})
