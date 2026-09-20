import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router-dom'
import Editor, { type Monaco, type OnMount } from '@monaco-editor/react'
import ReactMarkdown from 'react-markdown'
import {
  api,
  isAbortError,
  type ChallengeDetail,
  type RunHistoryEntry,
  type RunMeta,
  type RunResult,
} from '../api'
import { LoadError } from '../components/LoadError'
import { PageLoading } from '../components/PageLoading'
import { defineGreenlineTheme } from '../monacoTheme'
import { formatRunFailureOutput } from '../runFailure'
import {
  revealEditorLocation,
  selectInitialEditableFile,
  updateTestResultMarkers,
  type WorkspaceEditor,
} from '../editorDiagnostics'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  clearTimer,
  elapsedMs,
  formatClock,
  loadTimer,
  pauseTimer,
  setTimerDuration,
  startTimer,
  stopTimer,
  type TimerState,
} from '../timer'

function languageFor(path: string): string {
  if (path.endsWith('.py')) return 'python'
  if (path.endsWith('.js') || path.endsWith('.mjs') || path.endsWith('.cjs')) return 'javascript'
  if (path.endsWith('.ts') || path.endsWith('.tsx')) return 'typescript'
  if (path.endsWith('.jsx')) return 'javascript'
  if (path.endsWith('.md')) return 'markdown'
  if (path.endsWith('.json')) return 'json'
  return 'plaintext'
}

function Timer({
  slug,
  suggestedMinutes,
  state,
  onChange,
}: {
  slug: string
  suggestedMinutes: number
  state: TimerState
  onChange: (state: TimerState) => void
}) {
  const [, tick] = useState(0)
  const [open, setOpen] = useState(false)
  const running = state.status === 'running'

  useEffect(() => {
    if (!running) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [running])

  const budget = state.durationMinutes * 60_000
  const remaining = budget - elapsedMs(state)
  const over = remaining < 0
  const warn = !over && remaining <= budget * 0.25
  const idle = state.status === 'idle'
  const paused = state.status === 'paused'
  const complete = state.status === 'complete'
  const title = idle
    ? 'set timer'
    : paused
      ? 'timer paused'
      : complete
        ? 'final time'
        : 'time remaining'

  function begin(minutes: number) {
    const configured = setTimerDuration(slug, state, minutes)
    onChange(startTimer(slug, configured))
    setOpen(false)
  }

  function reset() {
    onChange(setTimerDuration(slug, state, state.durationMinutes))
  }

  function handleTimerClick() {
    if (idle) {
      setOpen((value) => !value)
      return
    }
    if (complete) {
      reset()
      setOpen(true)
      return
    }
    onChange(running ? pauseTimer(slug, state) : startTimer(slug, state))
  }

  return (
    <div className="relative flex items-center gap-1">
      <button
        type="button"
        className={cn(
          'min-h-11 border px-2.5 py-1 font-mono text-[11px] font-semibold tabular-nums transition-colors hover:border-foreground/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8',
          idle ? 'rounded-md' : 'rounded-full',
          !idle && over && 'border-destructive/25 bg-destructive/10 text-destructive',
          !idle && !over && warn && 'border-warning/25 bg-warning/10 text-warning',
          (idle || (!over && !warn)) && 'border-border bg-muted text-muted-foreground',
          (paused || complete) && 'opacity-80',
        )}
        title={title}
        aria-label={
          idle ? 'Set timer' : running ? 'Pause timer' : paused ? 'Resume timer' : 'Change timer'
        }
        aria-haspopup={idle ? 'dialog' : undefined}
        aria-expanded={idle ? open : undefined}
        onClick={handleTimerClick}
      >
        {idle
          ? '⏱ Set timer'
          : complete
            ? `⏱ ${formatClock(elapsedMs(state))}`
            : over
              ? `⏱ +${formatClock(remaining)} over${paused ? ' · paused' : ''}`
              : `⏱ ${formatClock(remaining)}${paused ? ' · paused' : ''}`}
      </button>

      {paused && (
        <button
          type="button"
          className="grid size-11 place-items-center rounded-full text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:size-8"
          title="reset timer"
          aria-label="Reset timer"
          onClick={reset}
        >
          ↺
        </button>
      )}

      {open && idle && (
        <div
          role="dialog"
          aria-label="Timer controls"
          className="absolute right-0 top-[calc(100%+0.5rem)] z-50 w-56 rounded-md border bg-card p-3 text-sm shadow-elevated"
        >
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold text-foreground">Timer</p>
            <span className="text-[11px] text-muted-foreground">~{suggestedMinutes} min suggested</span>
            <button
              type="button"
              className="ml-auto grid size-11 place-items-center rounded-sm text-xs text-muted-foreground hover:bg-muted hover:text-foreground sm:size-6"
              aria-label="Close timer controls"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-1 rounded-md bg-muted p-1">
            {(suggestedMinutes === 45 ? [15, 30, 45] : [15, suggestedMinutes, 45]).map((minutes) => (
              <button
                key={minutes}
                type="button"
                className={cn(
                  'h-11 rounded-sm px-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:h-7',
                  suggestedMinutes === minutes
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-card hover:text-foreground',
                )}
                aria-label={`Start ${minutes} minute timer`}
                onClick={() => begin(minutes)}
              >
                {minutes}m
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function formatSession(ms: number | null | undefined): string {
  if (ms == null) return '—'
  return formatClock(ms)
}

function formatUnsuccessfulRun(
  run: Pick<RunMeta, 'passed' | 'failed' | 'errors'>,
): string {
  const parts: string[] = []
  if (run.errors) parts.push(`${run.errors} error${run.errors === 1 ? '' : 's'}`)
  if (run.failed) parts.push(`${run.failed} failed`)
  if (run.passed) parts.push(`${run.passed} passed`)
  return parts.length ? parts.join(' · ') : 'No tests completed'
}

function HistoryRow({
  run,
  selected,
  onSelect,
  onRestore,
  restoring,
  restoreDisabled,
}: {
  run: RunHistoryEntry
  selected: boolean
  onSelect: () => void
  onRestore: () => void
  restoring: boolean
  restoreDisabled: boolean
}) {
  const when = new Date(run.started_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  return (
    <div
      className={cn(
        'grid grid-cols-[minmax(0,1fr)_auto] items-center border-b transition-colors hover:bg-muted/70',
        selected && 'bg-primary/8',
      )}
    >
      <button
        type="button"
        className="grid min-w-0 grid-cols-[20px_64px_minmax(100px,1fr)] items-center gap-2 px-4 py-2.5 text-left font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:grid-cols-[20px_72px_minmax(120px,1fr)_64px_82px]"
        onClick={onSelect}
        aria-label={`View run ${run.id}: ${formatUnsuccessfulRun(run)}`}
      >
        <span className={run.green ? 'text-success' : 'text-destructive'}>
          {run.green ? '✓' : '✗'}
        </span>
        <span className="text-muted-foreground">{when}</span>
        <span className="truncate text-foreground">
          {run.green
            ? `${run.passed} passed`
            : formatUnsuccessfulRun(run)}
        </span>
        <span className="hidden text-right text-muted-foreground sm:block" title="pytest wall time">
          {run.duration_ms}ms
        </span>
        <span className="hidden text-right text-muted-foreground sm:block" title="session timer at run">
          ⏱ {formatSession(run.session_elapsed_ms)}
        </span>
      </button>
      <button
        type="button"
        className="mr-3 rounded border border-border px-2 py-1 font-mono text-[10px] font-semibold text-muted-foreground hover:border-primary/60 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        onClick={onRestore}
        disabled={!run.snapshot_available || restoreDisabled}
        title={!run.snapshot_available ? 'Code snapshot unavailable for this older run' : `Restore code from run ${run.id}`}
        aria-label={`Restore code from run ${run.id}`}
      >
        {restoring ? 'RESTORING…' : 'RESTORE'}
      </button>
    </div>
  )
}

function OutputLine({ line }: { line: string }) {
  let cls = ''
  if (/PASSED|passed/.test(line) && !/failed/.test(line)) cls = 'text-console-success'
  else if (/FAILED|ERROR|failed|error/.test(line)) cls = 'text-console-error'
  else if (/^(=|_)+/.test(line.trim())) cls = 'text-console-muted'
  return <span className={cls}>{line + '\n'}</span>
}

function RunGuidance({
  result,
  onJump,
}: {
  result: RunResult
  onJump: (file: string, line: number) => void
}) {
  if (result.green) {
    return (
      <div className="border-b border-console-success/20 px-4 py-4 text-sm text-console-success">
        Every test is green. The challenge is solved.
      </div>
    )
  }

  const firstFailure = result.tests.find(
    (test) => test.outcome === 'failed' || test.outcome === 'error',
  )
  if (!firstFailure) return null

  const testName = firstFailure.id.split('::').at(-1) || firstFailure.id
  const file = firstFailure.file || firstFailure.id.split('::')[0] || null
  const jumpFile = firstFailure.crash_file || file
  const jumpLine = firstFailure.crash_line || firstFailure.line

  return (
    <div className="border-b border-white/10 px-4 py-2.5 text-xs leading-5 text-console-foreground">
      <p>
        <span className="font-semibold text-console-success">Start here:</span>{' '}
        <code className="text-console-warning">{testName}</code>
      </p>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-console-muted">
        {jumpFile && (
          jumpLine ? (
            <button
              type="button"
              className="font-mono underline decoration-transparent underline-offset-4 hover:text-console-foreground hover:decoration-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title={`open ${jumpFile} at line ${jumpLine}`}
              onClick={() => onJump(jumpFile, jumpLine)}
            >
              {jumpFile}:{jumpLine}
            </button>
          ) : (
            <span className="font-mono">{jumpFile}</span>
          )
        )}
        <span>Fix this test, then run again.</span>
      </div>
    </div>
  )
}

function shortName(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

const OUTPUT_HEIGHT_MIN = 20
const OUTPUT_HEIGHT_MAX = 80
const OUTPUT_HEIGHT_DEFAULT = 40

export default function Workspace() {
  const { slug = '' } = useParams()
  const navigate = useNavigate()
  const [challenge, setChallenge] = useState<ChallengeDetail | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [sideTab, setSideTab] = useState<'brief' | 'files'>('brief')
  const [openPath, setOpenPath] = useState<string>('')
  const [openTabs, setOpenTabs] = useState<string[]>([])
  const [contents, setContents] = useState<Record<string, string>>({})
  const [dirty, setDirty] = useState<Set<string>>(new Set())
  const [savedFlash, setSavedFlash] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<RunResult | null>(null)
  const [outputOpen, setOutputOpen] = useState(false)
  const [outputHeight, setOutputHeight] = useState(OUTPUT_HEIGHT_DEFAULT)
  const [timer, setTimer] = useState<TimerState | null>(null)
  const [drawerTab, setDrawerTab] = useState<'results' | 'history'>('results')
  const [runs, setRuns] = useState<RunHistoryEntry[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runsError, setRunsError] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [restoringRunId, setRestoringRunId] = useState<number | null>(null)
  const [restoreError, setRestoreError] = useState('')
  const [solutionAccessError, setSolutionAccessError] = useState('')
  const [newPath, setNewPath] = useState('')
  const [fileOpError, setFileOpError] = useState('')
  /** Narrow viewports: side panel toggled; desktop CSS ignores this. */
  const [mobileSideOpen, setMobileSideOpen] = useState(false)
  const contentsRef = useRef(contents)
  const dirtyRef = useRef(dirty)
  const openPathRef = useRef(openPath)
  const resultRef = useRef(result)
  const editorRef = useRef<WorkspaceEditor | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const modelListenerRef = useRef<{ dispose: () => void } | null>(null)
  const pendingRevealRef = useRef<{ path: string; line: number } | null>(null)
  const saveCurrentRef = useRef<() => Promise<void>>(async () => {})
  const pendingSavesRef = useRef(new Set<Promise<unknown>>())
  const restoreInProgressRef = useRef(false)
  const runInProgressRef = useRef(false)
  const skipUnsavedRef = useRef(false)
  const outputSectionRef = useRef<HTMLElement | null>(null)
  const outputResizeRef = useRef<{
    pointerId: number
    startY: number
    startHeight: number
    containerHeight: number
  } | null>(null)

  const blocker = useBlocker(dirty.size > 0)

  useEffect(() => {
    contentsRef.current = contents
  }, [contents])

  useEffect(() => {
    dirtyRef.current = dirty
  }, [dirty])

  useEffect(() => {
    openPathRef.current = openPath
  }, [openPath])

  useEffect(() => {
    resultRef.current = result
  }, [result])

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current.size === 0) return
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  useEffect(() => {
    if (blocker.state !== 'blocked') return
    if (skipUnsavedRef.current) {
      skipUnsavedRef.current = false
      blocker.proceed()
      return
    }
    const ok = window.confirm('You have unsaved changes. Leave anyway?')
    if (ok) blocker.proceed()
    else blocker.reset()
  }, [blocker])

  const revealPending = useCallback(() => {
    const pending = pendingRevealRef.current
    const editor = editorRef.current
    if (!pending || !editor) return
    if (!revealEditorLocation(editor, pending)) return
    pendingRevealRef.current = null
  }, [])

  const updateEditorMarkers = useCallback(() => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    if (!editor || !monaco) return
    updateTestResultMarkers(monaco, editor, resultRef.current?.tests ?? [])
  }, [])

  const openFile = useCallback(
    async (path: string, signal?: AbortSignal) => {
      setFileOpError('')
      let content = contentsRef.current[path]
      if (content === undefined) {
        try {
          content = await api.getFile(slug, path, { signal })
        } catch (err) {
          if (!isAbortError(err)) setFileOpError('could not open file')
          return false
        }
        if (signal?.aborted) return false
        setContents((c) => ({ ...c, [path]: content }))
      }
      setOpenPath(path)
      setOpenTabs((tabs) => (tabs.includes(path) ? tabs : [...tabs, path]))
      setSideTab('files')
      // On narrow layouts, opening a file should reveal the editor.
      setMobileSideOpen(false)
      return true
    },
    [slug],
  )

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const detail = await api.getChallenge(slug, { signal })
      if (signal?.aborted) return
      setChallenge(detail)
      // The estimate seeds an idle timer; only the learner starts the clock.
      const t = loadTimer(slug, detail.minutes)
      setTimer(detail.progress.status === 'solved' ? stopTimer(slug, t) : t)
      const first = selectInitialEditableFile(detail.files)
      if (first) {
        const opened = await openFile(first.path, signal)
        if (signal?.aborted) return
        if (!opened) throw new Error(`could not open ${first.path}`)
      }
    },
    [slug, openFile],
  )

  const refreshRuns = useCallback(
    async (signal?: AbortSignal) => {
      setRunsLoading(true)
      setRunsError(false)
      try {
        const list = await api.listRuns(slug, { signal })
        if (signal?.aborted) return
        setRuns(list.slice(0, 10))
      } catch (err) {
        if (isAbortError(err)) return
        console.error(err)
        setRunsError(true)
      } finally {
        if (!signal?.aborted) setRunsLoading(false)
      }
    },
    [slug],
  )

  useEffect(() => {
    const ac = new AbortController()
    void Promise.resolve()
      .then(() => load(ac.signal))
      .catch((err) => {
        if (!isAbortError(err)) setLoadError(true)
      })
    void Promise.resolve().then(() => refreshRuns(ac.signal))
    return () => ac.abort()
  }, [load, refreshRuns])

  async function refreshFiles() {
    const detail = await api.getChallenge(slug)
    setChallenge((ch) => (ch ? { ...ch, files: detail.files, creatable: detail.creatable } : detail))
  }

  function closeTab(path: string, e?: React.MouseEvent) {
    e?.stopPropagation()
    setOpenTabs((tabs) => {
      const next = tabs.filter((t) => t !== path)
      if (openPathRef.current === path) {
        const idx = tabs.indexOf(path)
        const fallback = next[idx - 1] ?? next[idx] ?? next[0] ?? ''
        setOpenPath(fallback)
      }
      return next
    })
  }

  function jumpTo(path: string, line: number) {
    pendingRevealRef.current = { path, line }
    openFile(path).then((opened) => {
      if (opened) requestAnimationFrame(revealPending)
    })
  }

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      revealPending()
      updateEditorMarkers()
    })
    return () => cancelAnimationFrame(frame)
  }, [openPath, contents, result, revealPending, updateEditorMarkers])

  function onEdit(value: string | undefined) {
    if (value === undefined || !openPath) return
    const meta = challenge?.files.find((f) => f.path === openPath)
    if (meta?.readonly) return
    setContents((c) => {
      const next = { ...c, [openPath]: value }
      contentsRef.current = next
      return next
    })
    setDirty((d) => {
      const next = new Set(d).add(openPath)
      dirtyRef.current = next
      return next
    })
  }

  function trackedSave(path: string, content: string) {
    const request = api.saveFile(slug, path, content)
    pendingSavesRef.current.add(request)
    void request.then(
      () => pendingSavesRef.current.delete(request),
      () => pendingSavesRef.current.delete(request),
    )
    return request
  }

  async function saveAll() {
    if (restoreInProgressRef.current) return
    const paths = [...dirtyRef.current].filter((p) => {
      const meta = challenge?.files.find((f) => f.path === p)
      return !meta?.readonly
    })
    if (paths.length === 0) {
      // Drop dirty marks on readonly files — they cannot be saved and would
      // 403 the whole run if we tried.
      setDirty((d) => {
        const next = new Set(d)
        for (const p of dirtyRef.current) {
          const meta = challenge?.files.find((f) => f.path === p)
          if (meta?.readonly) next.delete(p)
        }
        dirtyRef.current = next
        return next
      })
      return
    }
    const pending = paths.map((path) => ({ path, content: contentsRef.current[path] ?? '' }))
    await Promise.all(pending.map(({ path, content }) => trackedSave(path, content)))
    setDirty((d) => {
      const next = new Set(d)
      for (const { path, content } of pending) {
        if (contentsRef.current[path] === content) next.delete(path)
      }
      dirtyRef.current = next
      return next
    })
    setChallenge((ch) =>
      ch
        ? {
            ...ch,
            files: ch.files.map((f) =>
              paths.includes(f.path) ? { ...f, edited: true } : f,
            ),
          }
        : ch,
    )
  }

  async function saveCurrent() {
    if (restoreInProgressRef.current) return
    const path = openPathRef.current
    if (!path || !dirtyRef.current.has(path)) return
    const meta = challenge?.files.find((f) => f.path === path)
    if (meta?.readonly) return
    const content = contentsRef.current[path] ?? ''
    await trackedSave(path, content)
    const savedCurrentContent = contentsRef.current[path] === content
    setDirty((d) => {
      const next = new Set(d)
      if (savedCurrentContent) next.delete(path)
      dirtyRef.current = next
      return next
    })
    setChallenge((ch) =>
      ch
        ? {
            ...ch,
            files: ch.files.map((f) => (f.path === path ? { ...f, edited: true } : f)),
          }
        : ch,
    )
    if (savedCurrentContent) {
      setSavedFlash(true)
      window.setTimeout(() => setSavedFlash(false), 1200)
    }
  }
  useEffect(() => {
    saveCurrentRef.current = saveCurrent
  })

  const onEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco
    modelListenerRef.current?.dispose()
    modelListenerRef.current = editor.onDidChangeModel(() => {
      // Monaco's model-change event is the reliable boundary for a file jump;
      // React state and the asynchronous file fetch can commit in either order.
      requestAnimationFrame(() => {
        revealPending()
        updateEditorMarkers()
      })
    })
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      void saveCurrentRef.current()
    })
    revealPending()
    updateEditorMarkers()
  }

  useEffect(
    () => () => {
      modelListenerRef.current?.dispose()
      modelListenerRef.current = null
      editorRef.current = null
      monacoRef.current = null
    },
    [],
  )

  async function runTests() {
    if (restoreInProgressRef.current || runInProgressRef.current) return
    runInProgressRef.current = true
    setRunning(true)
    setOutputOpen(true)
    setDrawerTab('results')
    let streamedOutput = ''
    try {
      await saveAll()
      if (restoreInProgressRef.current) return
      const sessionMs = timer && timer.status !== 'idle' ? elapsedMs(timer) : undefined
      const job = await api.startRun(slug, sessionMs)
      let offset = 0
      let streamTruncated = false
      let r: RunResult | undefined
      while (!r) {
        const snapshot = await api.getRunJob(job.job_id, offset)
        offset = snapshot.next_offset
        streamTruncated ||= !!snapshot.output_truncated
        if (snapshot.output) {
          streamedOutput = (streamedOutput + snapshot.output).slice(-20_000)
          setResult({
            exit_code: -1,
            green: false,
            output: streamedOutput,
            output_truncated: streamTruncated,
            tests: [],
            passed: 0,
            failed: 0,
            errors: 0,
            skipped: 0,
          })
        }
        if (snapshot.status === 'failed') {
          throw new Error(snapshot.error || 'run job failed')
        }
        if (snapshot.status === 'completed') {
          if (!snapshot.result) throw new Error('run completed without a result')
          r = snapshot.result
          break
        }
        await new Promise((resolve) => window.setTimeout(resolve, 100))
      }
      setResult(r)
      if (r.run?.id != null) setSelectedRunId(r.run.id)
      if (r.green) {
        setTimer((t) => (t ? stopTimer(slug, t, sessionMs) : t))
      }
      if (challenge) {
        setChallenge({
          ...challenge,
          progress: {
            status: r.green ? 'solved' : challenge.progress.status === 'solved' ? 'solved' : 'attempted',
            attempts: challenge.progress.attempts + 1,
            spoiled: challenge.progress.spoiled,
          },
        })
      }
      await refreshRuns()
    } catch (err) {
      console.error(err)
      const message =
        err instanceof Error ? err.message : 'run failed — is the backend up on :8000?'
      setResult({
        exit_code: -1,
        green: false,
        output: formatRunFailureOutput(message, streamedOutput),
        output_truncated: false,
        tests: [],
        passed: 0,
        failed: 0,
        errors: 1,
        skipped: 0,
      })
    } finally {
      runInProgressRef.current = false
      setRunning(false)
    }
  }

  async function createNewFile() {
    const path = newPath.trim().replace(/^\//, '')
    if (!path) return
    setFileOpError('')
    try {
      await api.createFile(slug, path)
      setNewPath('')
      await refreshFiles()
      await openFile(path)
    } catch {
      setFileOpError('could not create — must be under an allowed prefix')
    }
  }

  async function removeCreatedFile(path: string) {
    if (dirtyRef.current.has(path) && !window.confirm('You have unsaved changes. Delete this file anyway?')) {
      return
    }
    setFileOpError('')
    try {
      await api.deleteFile(slug, path)
      setContents((c) => {
        const next = { ...c }
        delete next[path]
        return next
      })
      setDirty((d) => {
        const next = new Set(d)
        next.delete(path)
        return next
      })
      setOpenTabs((tabs) => tabs.filter((t) => t !== path))
      if (openPath === path) setOpenPath('')
      await refreshFiles()
    } catch {
      setFileOpError('could not delete file')
    }
  }

  async function resetAll() {
    if (dirty.size > 0 && !confirm('You have unsaved changes. Reset anyway?')) return
    else if (dirty.size === 0 && !confirm('Reset this challenge? Your edits and progress will be discarded.'))
      return
    await api.reset(slug)
    setContents({})
    setDirty(new Set())
    setOpenTabs([])
    setOpenPath('')
    setResult(null)
    setRuns([])
    setRunsLoading(false)
    setRunsError(false)
    setSelectedRunId(null)
    setRestoringRunId(null)
    setRestoreError('')
    setTimer(clearTimer(slug, challenge?.minutes ?? timer?.durationMinutes ?? 25))
    await load()
  }

  function showHistoricalRun(run: RunHistoryEntry) {
    setSelectedRunId(run.id)
    setResult({
      exit_code: run.exit_code,
      green: run.green,
      output: run.output_tail,
      output_truncated: run.output_truncated,
      tests: run.tests,
      passed: run.passed,
      failed: run.failed,
      errors: run.errors,
      skipped: run.skipped,
      duration_ms: run.duration_ms,
      run,
    })
    setDrawerTab('results')
  }

  async function restoreHistoricalRun(run: RunHistoryEntry) {
    if (
      !run.snapshot_available ||
      restoreInProgressRef.current ||
      runInProgressRef.current
    ) return
    const confirmed = window.confirm(
      `Restore code from run ${run.id}? Your current workspace files will be replaced.`,
    )
    if (!confirmed) return

    restoreInProgressRef.current = true
    setRestoringRunId(run.id)
    setRestoreError('')
    try {
      await Promise.allSettled([...pendingSavesRef.current])
      await api.restoreRun(slug, run.id)
      contentsRef.current = {}
      dirtyRef.current = new Set()
      openPathRef.current = ''
      setContents({})
      setDirty(new Set())
      setOpenTabs([])
      setOpenPath('')

      const detail = await api.getChallenge(slug)
      setChallenge(detail)
      const first = selectInitialEditableFile(detail.files)
      if (first) await openFile(first.path)
      showHistoricalRun(run)
    } catch (err) {
      console.error(err)
      setRestoreError('could not restore this run’s code snapshot')
    } finally {
      restoreInProgressRef.current = false
      setRestoringRunId(null)
    }
  }

  if (loadError) {
    return (
      <LoadError
        onRetry={() => {
          setLoadError(false)
          setChallenge(null)
          load().catch(() => setLoadError(true))
        }}
      />
    )
  }

  if (!challenge)
    return <PageLoading label="Opening workspace…" />

  const openFileMeta = challenge.files.find((f) => f.path === openPath)
  const solved = challenge.progress.status === 'solved'
  const alreadyOpen = solved || !!challenge.progress.spoiled

  async function handleSolutionNav(e: React.MouseEvent) {
    setSolutionAccessError('')
    if (dirty.size > 0 && !window.confirm('You have unsaved changes. Leave anyway?')) {
      e.preventDefault()
      return
    }
    if (alreadyOpen) {
      if (dirty.size > 0) skipUnsavedRef.current = true
      return
    }
    e.preventDefault()
    if (!window.confirm('Viewing the solution marks this challenge as spoiled — attempt it first?')) {
      return
    }
    try {
      const { progress } = await api.spoil(slug)
      setChallenge((ch) => (ch ? { ...ch, progress } : ch))
    } catch {
      setSolutionAccessError('Could not unlock the solution. Your progress was not changed. Try again.')
      return
    }
    if (dirty.size > 0) skipUnsavedRef.current = true
    navigate(`/c/${slug}/solution`)
  }

  return (
    <div className="workspace-shell flex h-svh min-w-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="workspace-topbar shrink-0 border-b bg-card px-3 py-2 md:px-4">
        <div className="flex w-full flex-wrap items-center gap-2">
          <Link
            to="/challenges"
            className="inline-flex min-h-9 items-center gap-2 rounded-md px-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span aria-hidden="true">←</span>
            <span className="hidden sm:inline">Challenges</span>
          </Link>
          <span className="hidden h-4 w-px bg-border sm:block" aria-hidden="true" />
          <span className="hidden text-xs font-semibold tracking-[0.01em] text-muted-foreground sm:inline">
            Workspace
          </span>
          <div className="flex-1" />
          <span className="hidden items-center gap-1.5 text-[11px] text-muted-foreground lg:flex">
            <span className="size-1.5 rounded-full bg-success" aria-hidden="true" /> autosaved
          </span>
          {timer && (
            <Timer
              slug={slug}
              suggestedMinutes={challenge.minutes}
              state={timer}
              onChange={setTimer}
            />
          )}
          <Button
            type="button"
            variant={mobileSideOpen ? 'primary' : 'utility'}
            size="sm"
            className="max-lg:min-h-11 lg:hidden"
            onClick={() => setMobileSideOpen((o) => !o)}
            aria-expanded={mobileSideOpen}
            aria-controls="ws-side-panel"
          >
            {mobileSideOpen ? 'Hide panel' : 'Panel'}
          </Button>
          <Button type="button" variant="ghost" size="sm" className="text-destructive max-sm:min-h-11" onClick={resetAll}>
            Reset
          </Button>
          {savedFlash && <span className="rounded-full bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">saved</span>}
          <Link
            to={`/c/${slug}/solution`}
            className="inline-flex min-h-9 items-center justify-center rounded-md border border-border bg-card px-3.5 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring max-sm:min-h-11"
            onClick={(e) => void handleSolutionNav(e)}
          >
            Solution
          </Link>
          <Button type="button" variant="primary" size="sm" className="px-4 max-sm:min-h-11" onClick={runTests} disabled={running || restoringRunId !== null}>
            {running ? 'Running…' : '▶ Run tests'}
          </Button>
        </div>
      </header>

      <div className="workspace-context shrink-0 border-b bg-background px-4 py-3 md:px-5 md:py-4">
        <div className="w-full" role="group" aria-label="Challenge details">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="truncate text-xl font-bold tracking-[-0.025em] md:text-2xl">{challenge.title}</h1>
              <span className={cn(
                'rounded-full px-2.5 py-1 text-[10px] font-bold',
                challenge.progress.status === 'solved' && 'bg-success/10 text-success',
                challenge.progress.status === 'attempted' && 'bg-warning/10 text-warning',
                challenge.progress.status === 'todo' && 'bg-muted text-muted-foreground',
              )}>
                {solved ? '● SOLVED' : challenge.progress.status === 'attempted' ? '◐ ATTEMPTED' : '○ TODO'}
              </span>
            </div>
            <p className="mt-0.5 max-w-3xl text-sm leading-5 text-muted-foreground">{challenge.blurb}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              <span className="font-semibold text-foreground">{challenge.type}</span>
              <span aria-hidden="true">·</span>
              <span>{challenge.difficulty}</span>
              <span aria-hidden="true">·</span>
              <span>{challenge.language}</span>
              <span aria-hidden="true">·</span>
              <span>~{challenge.minutes} min</span>
              <span aria-hidden="true">·</span>
              <span>{challenge.progress.attempts} {challenge.progress.attempts === 1 ? 'attempt' : 'attempts'}</span>
            </div>
            {(challenge.variants?.length ?? 0) > 1 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5" role="group" aria-label="Challenge language">
                <span className="mr-1 text-xs font-medium text-muted-foreground">Language</span>
                {challenge.variants?.map((variant) => {
                  const selected = variant.slug === slug
                  return (
                    <button
                      key={variant.id}
                      type="button"
                      aria-pressed={selected}
                      className={cn(
                        'min-h-8 rounded-full border px-3 text-xs font-semibold transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        selected && 'border-primary bg-primary text-primary-foreground hover:text-primary-foreground',
                      )}
                      onClick={() => {
                        if (!selected) navigate(`/c/${variant.slug}`, { replace: true })
                      }}
                    >
                      {variant.language}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {solutionAccessError && (
        <div
          className="shrink-0 border-b border-destructive/20 bg-destructive/5 px-4 py-2 text-sm text-destructive md:px-6"
          role="alert"
        >
          {solutionAccessError}
        </div>
      )}

      {solved && (
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-success/20 bg-success/10 px-4 py-2 text-sm text-success md:px-6">
          <span>All tests green. Nice.</span>
          <Link
            to={`/c/${slug}/solution`}
            className="font-medium underline underline-offset-4"
            onClick={(e) => void handleSolutionNav(e)}
          >
            Compare with the reference solution →
          </Link>
        </div>
      )}

      <div className="relative grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[296px_minmax(0,1fr)]">
        <aside
          className={cn(
            'workspace-sidebar min-h-0 w-full flex-col overflow-hidden border-b bg-card lg:static lg:z-auto lg:flex lg:w-auto lg:border-r lg:border-b-0',
            mobileSideOpen ? 'absolute inset-0 z-30 flex' : 'hidden',
          )}
          id="ws-side-panel"
        >
          <div className="grid h-11 shrink-0 grid-cols-2 border-b bg-muted/35 px-2" role="group" aria-label="Workspace panel">
            <button
              type="button"
              aria-pressed={sideTab === 'brief'}
              className={cn(
                'border-b-2 border-transparent px-2 text-xs font-semibold text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                sideTab === 'brief' && 'border-primary text-foreground',
              )}
              onClick={() => setSideTab('brief')}
            >
              Brief
            </button>
            <button
              type="button"
              aria-pressed={sideTab === 'files'}
              className={cn(
                'border-b-2 border-transparent px-2 text-xs font-semibold text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                sideTab === 'files' && 'border-primary text-foreground',
              )}
              onClick={() => setSideTab('files')}
            >
              Files
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto bg-card">
            {sideTab === 'brief' ? (
              <div className="workspace-prose p-5">
                <div className="mb-5 flex flex-wrap gap-1.5">
                  <span className="rounded-full border px-2 py-1 text-[11px] text-muted-foreground">~{challenge.minutes} min</span>
                  <span className="rounded-full border px-2 py-1 text-[11px] text-muted-foreground">{challenge.language}</span>
                  <span className="rounded-full border px-2 py-1 text-[11px] text-muted-foreground">attempts: {challenge.progress.attempts}</span>
                </div>
                <ReactMarkdown>{challenge.brief}</ReactMarkdown>
              </div>
            ) : (
              <>
                {!!challenge.creatable?.length && (
                  <form
                    className="border-b p-3"
                    onSubmit={(e) => {
                      e.preventDefault()
                      void createNewFile()
                    }}
                  >
                    <div className="mb-2 text-[11px] font-semibold text-muted-foreground">+ new file</div>
                    <div className="flex gap-2">
                      <input
                        className="min-h-9 min-w-0 flex-1 rounded-md border bg-background px-2 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/15"
                        value={newPath}
                        onChange={(e) => setNewPath(e.target.value)}
                        placeholder={`${challenge.creatable[0].replace(/\/?$/, '/')}module.py`}
                        aria-label="new file path"
                      />
                      <Button type="submit" variant="utility" size="sm" disabled={!newPath.trim()}>
                        add
                      </Button>
                    </div>
                    <div className="mt-2 truncate font-mono text-[10px] text-muted-foreground">
                      under {challenge.creatable.map((p) => p.replace(/\/?$/, '/')).join(', ')}
                    </div>
                  </form>
                )}
                {fileOpError && <div className="bg-destructive/10 px-3 py-2 text-xs text-destructive">{fileOpError}</div>}
                {challenge.files.map((f) => (
                  <div key={f.path} className="group flex items-center border-b last:border-b-0">
                    <button
                      type="button"
                      className={cn(
                        'flex min-h-11 min-w-0 flex-1 items-center gap-2 border-l-2 border-transparent px-3 text-left font-mono text-xs text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring lg:min-h-10',
                        f.path === openPath && 'border-l-primary bg-primary/8 text-foreground',
                      )}
                      onClick={() => openFile(f.path)}
                    >
                      {(dirty.has(f.path) || f.edited) && <span className="size-1.5 shrink-0 rounded-full bg-primary" />}
                      <span className="truncate">{f.path}</span>
                      {f.new && <span className="ml-auto rounded-sm bg-success/10 px-1.5 py-0.5 text-[9px] font-bold text-success">NEW</span>}
                      {f.readonly && <span className="ml-auto text-[9px] font-semibold text-muted-foreground">RO</span>}
                    </button>
                    {f.new && (
                      <button
                        type="button"
                        className="extend-touch-target mr-2 size-7 shrink-0 rounded-md text-muted-foreground opacity-70 hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100"
                        title="delete created file"
                        aria-label={`delete ${f.path}`}
                        onClick={() => void removeCreatedFile(f.path)}
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>
        </aside>

        <div className="workspace-editor flex min-h-0 min-w-0 flex-col overflow-hidden bg-console">
          <div className="flex h-11 shrink-0 items-stretch overflow-x-auto border-b border-white/10 bg-[#111713]">
            {openTabs.length === 0 ? (
              <span className="flex items-center px-4 font-mono text-xs text-console-muted">select a file</span>
            ) : (
              openTabs.map((path) => (
                <div key={path} className={cn('flex shrink-0 items-center border-r border-t-2 border-t-transparent border-white/10', path === openPath && 'border-t-primary bg-console-surface')}>
                  <button
                    type="button"
                    className={cn(
                      'h-full max-w-48 truncate px-3 font-mono text-xs text-console-muted hover:text-console-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                      path === openPath && 'text-console-foreground',
                    )}
                    onClick={() => setOpenPath(path)}
                    onMouseDown={(e) => {
                      if (e.button === 1) {
                        e.preventDefault()
                        closeTab(path)
                      }
                    }}
                    title={path}
                  >
                    {shortName(path)}
                    {dirty.has(path) ? ' •' : ''}
                  </button>
                  <button
                    type="button"
                    className="extend-touch-target mr-1 size-7 rounded-md text-console-muted hover:bg-white/10 hover:text-console-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={`close ${path}`}
                    onClick={(e) => closeTab(path, e)}
                  >
                    ×
                  </button>
                </div>
              ))
            )}
            <span className="ml-auto hidden shrink-0 items-center px-3 font-mono text-[10px] text-console-muted sm:flex">
              {openFileMeta?.readonly ? 'READ ONLY' : dirty.has(openPath) ? 'UNSAVED' : '⌘S TO SAVE'}
            </span>
          </div>
          {openFileMeta?.readonly && (
            <div className="shrink-0 border-b border-warning/20 bg-warning/10 px-4 py-1.5 text-center text-[11px] font-medium text-warning">
              read-only — tests are the spec, not the suspect
            </div>
          )}
          <div className="workspace-code min-h-[180px] flex-1 bg-console">
            <Editor
              path={openPath}
              language={languageFor(openPath)}
              value={contents[openPath] ?? ''}
              onChange={onEdit}
              beforeMount={defineGreenlineTheme}
              onMount={onEditorMount}
              theme="greenline"
              options={{
                readOnly: openFileMeta?.readonly ?? false,
                fontSize: 13.5,
                fontFamily: "'IBM Plex Mono', monospace",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                padding: { top: 14 },
                glyphMargin: true,
                renderLineHighlight: 'gutter',
              }}
            />
          </div>

          <section
            ref={outputSectionRef}
            className={cn(
              'workspace-output relative shrink overflow-hidden border-t bg-card',
              outputOpen ? 'min-h-[160px] max-h-[80%]' : 'h-10 transition-[height] duration-200',
            )}
            style={outputOpen ? { height: `${outputHeight}%` } : undefined}
            aria-label="Test output"
          >
            {outputOpen && (
              <div
                role="separator"
                aria-label="Resize test output"
                aria-orientation="horizontal"
                aria-valuemin={OUTPUT_HEIGHT_MIN}
                aria-valuemax={OUTPUT_HEIGHT_MAX}
                aria-valuenow={Math.round(outputHeight)}
                aria-valuetext={`${Math.round(outputHeight)} percent of the editor`}
                tabIndex={0}
                title="Drag to resize test output"
                className="group absolute -top-1.5 left-0 z-20 flex h-3 w-full cursor-row-resize touch-none items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                onPointerDown={(event) => {
                  const containerHeight =
                    outputSectionRef.current?.parentElement?.getBoundingClientRect().height ||
                    window.innerHeight
                  outputResizeRef.current = {
                    pointerId: event.pointerId,
                    startY: event.clientY,
                    startHeight: outputHeight,
                    containerHeight,
                  }
                  event.currentTarget.setPointerCapture(event.pointerId)
                }}
                onPointerMove={(event) => {
                  const resize = outputResizeRef.current
                  if (!resize || resize.pointerId !== event.pointerId) return
                  const delta = ((resize.startY - event.clientY) / resize.containerHeight) * 100
                  setOutputHeight(Math.min(
                    OUTPUT_HEIGHT_MAX,
                    Math.max(OUTPUT_HEIGHT_MIN, resize.startHeight + delta),
                  ))
                }}
                onPointerUp={(event) => {
                  if (outputResizeRef.current?.pointerId !== event.pointerId) return
                  outputResizeRef.current = null
                  event.currentTarget.releasePointerCapture(event.pointerId)
                }}
                onPointerCancel={() => {
                  outputResizeRef.current = null
                }}
                onLostPointerCapture={() => {
                  outputResizeRef.current = null
                }}
                onDoubleClick={() => setOutputHeight(OUTPUT_HEIGHT_DEFAULT)}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowUp') {
                    event.preventDefault()
                    setOutputHeight((height) => Math.min(OUTPUT_HEIGHT_MAX, height + 5))
                  } else if (event.key === 'ArrowDown') {
                    event.preventDefault()
                    setOutputHeight((height) => Math.max(OUTPUT_HEIGHT_MIN, height - 5))
                  } else if (event.key === 'Home') {
                    event.preventDefault()
                    setOutputHeight(OUTPUT_HEIGHT_MIN)
                  } else if (event.key === 'End') {
                    event.preventDefault()
                    setOutputHeight(OUTPUT_HEIGHT_MAX)
                  }
                }}
              >
                <span className="h-0.5 w-12 rounded-full bg-border transition-colors group-hover:bg-primary group-focus-visible:bg-primary" />
              </div>
            )}
            <div className="flex h-10 shrink-0 items-center gap-1 border-b px-2">
              <button
                type="button"
                className="size-8 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => setOutputOpen((o) => !o)}
                aria-label={outputOpen ? 'Collapse test output' : 'Expand test output'}
              >
                {outputOpen ? '▾' : '▸'}
              </button>
              <button
                type="button"
                className={cn(
                  'h-full border-b-2 border-transparent px-3 text-xs font-semibold text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                  drawerTab === 'results' && 'border-primary text-foreground',
                )}
                onClick={() => {
                  setDrawerTab('results')
                  setOutputOpen(true)
                }}
              >
                RESULTS
              </button>
              <button
                type="button"
                className={cn(
                  'h-full border-b-2 border-transparent px-3 text-xs font-semibold text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                  drawerTab === 'history' && 'border-primary text-foreground',
                )}
                onClick={() => {
                  setDrawerTab('history')
                  setOutputOpen(true)
                  void refreshRuns()
                }}
              >
                HISTORY{runs.length ? ` (${runs.length})` : ''}
              </button>
              {result && !running && drawerTab === 'results' && (
                <span className={cn(
                  'ml-auto rounded-full px-2.5 py-1 text-[11px] font-semibold',
                  result.green ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive',
                )}>
                  {result.green
                    ? `ALL GREEN — ${result.passed} passed`
                    : formatUnsuccessfulRun(result)}
                </span>
              )}
              {running && <span className="ml-2 animate-spin text-muted-foreground">◜</span>}
            </div>
            {outputOpen &&
              (drawerTab === 'history' ? (
                <div className="h-[calc(100%_-_2.5rem)] overflow-auto">
                  {restoreError && (
                    <div className="border-b border-destructive/20 px-4 py-2 text-xs text-destructive">
                      {restoreError}
                    </div>
                  )}
                  {runsLoading ? (
                    <div className="p-5 text-xs text-muted-foreground">loading run history…</div>
                  ) : runsError ? (
                    <div className="flex items-center gap-3 p-5 text-sm text-destructive">
                      <span>could not load run history</span>
                      <Button variant="utility" size="sm" type="button" onClick={() => void refreshRuns()}>
                        Retry
                      </Button>
                    </div>
                  ) : runs.length === 0 ? (
                    <div className="p-5 text-xs text-muted-foreground">no runs yet — hit ▶ Run tests</div>
                  ) : (
                    runs.map((run) => (
                      <HistoryRow
                        key={run.id}
                        run={run}
                        selected={run.id === selectedRunId}
                        onSelect={() => showHistoricalRun(run)}
                        onRestore={() => void restoreHistoricalRun(run)}
                        restoring={restoringRunId === run.id}
                        restoreDisabled={restoringRunId !== null || running}
                      />
                    ))
                  )}
                </div>
              ) : (
                <div
                  key={result?.run?.id != null ? `run-${result.run.id}` : running ? 'running' : 'result'}
                  aria-label="Test report"
                  className="h-[calc(100%_-_2.5rem)] overflow-auto bg-console [overflow-anchor:none] [scrollbar-gutter:stable]"
                >
                  {result ? (
                    <>
                      <RunGuidance result={result} onJump={jumpTo} />
                      {result.output_truncated && (
                        <div className="border-b border-console-warning/20 bg-console-warning/10 px-4 py-2 text-xs text-console-warning">
                          output truncated — showing the last 20,000 characters
                        </div>
                      )}
                      <pre className="m-0 whitespace-pre-wrap p-4 font-mono text-xs leading-5 text-console-foreground">
                        {result.output.split('\n').map((l, i) => (
                          <OutputLine key={i} line={l} />
                        ))}
                      </pre>
                    </>
                  ) : (
                    <div className="p-4 font-mono text-xs text-console-muted">
                      {running ? 'running pytest in sandbox…' : 'hit ▶ Run tests to execute the suite'}
                    </div>
                  )}
                </div>
              ))}
          </section>
        </div>
      </div>
    </div>
  )
}
