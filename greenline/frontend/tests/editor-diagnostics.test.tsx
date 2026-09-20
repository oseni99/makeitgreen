import React, { useEffect, useRef } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { TestCase } from '../src/api'
import {
  revealEditorLocation,
  selectInitialEditableFile,
  TEST_RESULT_MARKER_OWNER,
  updateTestResultMarkers,
  type WorkspaceEditor,
} from '../src/editorDiagnostics'
import { WorkspaceRoute } from '../src/pages/KeyedRoutes'

vi.mock('../src/monacoSetup', () => ({}))

const editorHarness = vi.hoisted(() => {
  const listeners = new Set<() => void>()
  const model = {
    uri: { path: '' },
    getLineCount: () => 20,
    getLineMaxColumn: () => 80,
  }
  return {
    listeners,
    model,
    revealLineInCenter: vi.fn(),
    setPosition: vi.fn(),
    focus: vi.fn(),
    setModelMarkers: vi.fn(),
    reset() {
      listeners.clear()
      model.uri.path = ''
      model.getLineCount = () => 20
      this.revealLineInCenter.mockReset()
      this.setPosition.mockReset()
      this.focus.mockReset()
      this.setModelMarkers.mockReset()
    },
  }
})

vi.mock('@monaco-editor/react', () => {
  const editor = {
    getModel: () => editorHarness.model,
    revealLineInCenter: editorHarness.revealLineInCenter,
    setPosition: editorHarness.setPosition,
    focus: editorHarness.focus,
    addCommand: vi.fn(),
    onDidChangeModel: (listener: () => void) => {
      editorHarness.listeners.add(listener)
      return { dispose: () => editorHarness.listeners.delete(listener) }
    },
  }
  const monaco = {
    KeyMod: { CtrlCmd: 1 },
    KeyCode: { KeyS: 2 },
    MarkerSeverity: { Error: 8 },
    editor: { setModelMarkers: editorHarness.setModelMarkers },
  }

  function MockEditor({ path, value, onMount }: {
      path: string
      value: string
      onMount?: (editor: typeof editor, monaco: typeof monaco) => void
  }) {
    const mounted = useRef(false)
    useEffect(() => {
      if (mounted.current) return
      mounted.current = true
      onMount?.(editor, monaco)
    }, [onMount])
    useEffect(() => {
      editorHarness.model.uri.path = `/${path}`
      editorHarness.listeners.forEach((listener) => listener())
    }, [path])
    return <textarea aria-label="code editor" readOnly value={value} />
  }

  return {
    default: MockEditor,
    DiffEditor: () => null,
  }
})

function testCase(overrides: Partial<TestCase>): TestCase {
  return {
    id: 'tests/test_checkout.py::test_checkout',
    outcome: 'failed',
    duration_ms: 1,
    file: 'tests/test_checkout.py',
    line: 4,
    message: 'inventory went negative',
    crash_file: 'orders/checkout.py',
    crash_line: 7,
    ...overrides,
  }
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  editorHarness.reset()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0)
    return 1
  })
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('workspace editor diagnostics', () => {
  it('selects an editable Node source file when a challenge has no Python files', () => {
    expect(selectInitialEditableFile([
      { path: 'README.md', readonly: true, edited: false },
      { path: 'tests/webhooks.test.js', readonly: true, edited: false },
      { path: 'src/webhooks.js', readonly: false, edited: false },
    ])?.path).toBe('src/webhooks.js')
  })

  it('reveals normalized Monaco model paths and clamps the target line', () => {
    editorHarness.model.uri.path = '/orders/my%20service.py'
    editorHarness.model.getLineCount = () => 5
    const editor = {
      getModel: () => editorHarness.model,
      revealLineInCenter: editorHarness.revealLineInCenter,
      setPosition: editorHarness.setPosition,
      focus: editorHarness.focus,
    } as unknown as WorkspaceEditor

    expect(revealEditorLocation(editor, { path: 'orders/my service.py', line: 12 })).toBe(true)
    expect(editorHarness.revealLineInCenter).toHaveBeenCalledWith(5)
    expect(editorHarness.setPosition).toHaveBeenCalledWith({ lineNumber: 5, column: 1 })
  })

  it('maps only failures for the active file into owned Monaco markers', () => {
    editorHarness.model.uri.path = '/orders/checkout.py'
    const editor = { getModel: () => editorHarness.model } as unknown as WorkspaceEditor
    const monaco = {
      MarkerSeverity: { Error: 8 },
      editor: { setModelMarkers: editorHarness.setModelMarkers },
    } as never

    updateTestResultMarkers(monaco, editor, [
      testCase({}),
      testCase({ id: 'passing', outcome: 'passed', message: '', crash_line: 8 }),
      testCase({ id: 'other', crash_file: 'orders/other.py', crash_line: 3 }),
    ])

    expect(editorHarness.setModelMarkers).toHaveBeenCalledWith(
      editorHarness.model,
      TEST_RESULT_MARKER_OWNER,
      [expect.objectContaining({
        severity: 8,
        message: 'inventory went negative',
        startLineNumber: 7,
        endLineNumber: 7,
      })],
    )
  })

  it('reveals the first-open failure after Monaco commits the target model', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/runs') && init?.method !== 'POST') return json({ runs: [] })
      if (url.endsWith('/runs') && init?.method === 'POST') {
        return json({ job_id: 'job-1', slug: 'orders-service', status: 'queued' })
      }
      if (url.startsWith('/api/run-jobs/job-1')) {
        return json({
          job_id: 'job-1',
          slug: 'orders-service',
          status: 'completed',
          output: '1 failed',
          next_offset: 8,
          result: {
            exit_code: 1,
            green: false,
            output: '1 failed',
            tests: [testCase({})],
            passed: 0,
            failed: 1,
            errors: 0,
            skipped: 0,
            run: { id: 1 },
          },
        })
      }
      if (url.includes('/files/')) return json({ content: '# source\n' })
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
          { path: 'orders/checkout.py', readonly: false, edited: false },
        ],
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const router = createMemoryRouter(
      [{ path: '/c/:slug', element: <WorkspaceRoute /> }],
      { initialEntries: ['/c/orders-service'] },
    )
    const user = userEvent.setup()
    render(<RouterProvider router={router} />)

    await screen.findByRole('textbox', { name: 'code editor' })
    await user.click(screen.getByRole('button', { name: /run tests/i }))
    const jump = await screen.findByTitle('open orders/checkout.py at line 7')
    expect(jump.textContent).toBe('orders/checkout.py:7')
    await user.click(jump)

    await waitFor(() => expect(editorHarness.revealLineInCenter).toHaveBeenCalledWith(7))
    expect(editorHarness.setPosition).toHaveBeenCalledWith({ lineNumber: 7, column: 1 })
    await waitFor(() => expect(editorHarness.setModelMarkers).toHaveBeenLastCalledWith(
      editorHarness.model,
      TEST_RESULT_MARKER_OWNER,
      [expect.objectContaining({ startLineNumber: 7 })],
    ))
  })
})
