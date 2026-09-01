import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router-dom'
import Editor, { type Monaco, type OnMount } from '@monaco-editor/react'
import ReactMarkdown from 'react-markdown'
import {
  api,
  isAbortError,
  type ChallengeDetail,
  type RunHistoryEntry,
  type RunResult,
  type SearchHit,
  type TestCase,
} from '../api'
import { LoadError } from '../components/LoadError'
import { defineGreenlineTheme } from '../monacoTheme'
import {
  revealEditorLocation,
  selectInitialEditableFile,
  updateTestResultMarkers,
  type WorkspaceEditor,
} from '../editorDiagnostics'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { cn } from '@/lib/utils'
import {
  clearTimer,
  elapsedMs,
  formatClock,
  loadTimer,
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

function Timer({ minutes, state }: { minutes: number; state: TimerState }) {
  const [, tick] = useState(0)
  const stopped = state.stoppedElapsed !== undefined

  useEffect(() => {
    if (stopped) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [stopped])

  const budget = minutes * 60_000
  const remaining = budget - elapsedMs(state)
  const over = remaining < 0
  const warn = !over && remaining <= budget * 0.25

  return (
    <span
      className={cn(
        'rounded-full border px-2.5 py-1 font-mono text-[11px] font-semibold tabular-nums',
        over && 'border-destructive/25 bg-destructive/10 text-destructive',
        warn && 'border-warning/25 bg-warning/10 text-warning',
        !over && !warn && 'border-border bg-muted text-muted-foreground',
        stopped && 'opacity-70',
      )}
      title={stopped ? 'final time' : 'time remaining'}
    >
      {stopped
        ? `⏱ ${formatClock(elapsedMs(state))}`
        : over
          ? `⏱ +${formatClock(remaining)} over`
          : `⏱ ${formatClock(remaining)}`}
    </span>
  )
}

function formatSession(ms: number | null | undefined): string {
  if (ms == null) return '—'
  return formatClock(ms)
}

function HistoryRow({
  run,
  selected,
  onSelect,
}: {
  run: RunHistoryEntry
  selected: boolean
  onSelect: () => void
}) {
  const when = new Date(run.started_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  return (
    <button
      type="button"
      className={cn(
        'grid w-full grid-cols-[20px_64px_minmax(100px,1fr)] items-center gap-2 border-b px-4 py-2.5 text-left font-mono text-xs transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:grid-cols-[20px_72px_minmax(120px,1fr)_64px_82px]',
        selected && 'bg-primary/8',
      )}
      onClick={onSelect}
    >
      <span className={run.green ? 'text-success' : 'text-destructive'}>
        {run.green ? '✓' : '✗'}
      </span>
      <span className="text-muted-foreground">{when}</span>
      <span className="truncate text-foreground">
        {run.green
          ? `${run.passed} passed`
          : `${run.failed} failed · ${run.passed} passed`}
      </span>
      <span className="hidden text-right text-muted-foreground sm:block" title="pytest wall time">
        {run.duration_ms}ms
      </span>
      <span className="hidden text-right text-muted-foreground sm:block" title="session timer at run">
        ⏱ {formatSession(run.session_elapsed_ms)}
      </span>
    </button>
  )
}

function OutputLine({ line }: { line: string }) {
  let cls = ''
  if (/PASSED|passed/.test(line) && !/failed/.test(line)) cls = 'text-console-success'
  else if (/FAILED|ERROR|failed|error/.test(line)) cls = 'text-console-error'
  else if (/^(=|_)+/.test(line.trim())) cls = 'text-console-muted'
  return <span className={cls}>{line + '\n'}</span>
}

const OUTCOME_ICONS: Record<string, [string, string]> = {
  passed: ['✓', 'text-success'],
  failed: ['✗', 'text-destructive'],
  error: ['⚠', 'text-destructive'],
  skipped: ['○', 'text-muted-foreground'],
  xfailed: ['○', 'text-muted-foreground'],
  xpassed: ['✓', 'text-warning'],
}

function TestRow({
  test,
  onJump,
}: {
  test: TestCase
  onJump: (file: string, line: number) => void
}) {
  const [icon, cls] = OUTCOME_ICONS[test.outcome] ?? ['?', 't-dim']
  const failed = test.outcome === 'failed' || test.outcome === 'error'
  // Prefer the crash site (often the source file) over the test definition.
  const target =
    test.crash_file && test.crash_line
      ? { file: test.crash_file, line: test.crash_line }
      : test.file && test.line
        ? { file: test.file, line: test.line }
        : null

  return (
    <div className="border-b px-4 py-3 last:border-b-0">
      <div className="flex min-w-0 items-center gap-2 font-mono text-xs">
        <span className={cn('w-4 shrink-0 font-bold', cls)}>{icon}</span>
        <span className={cn('min-w-0 flex-1 truncate', failed ? 'text-destructive' : 'text-foreground')}>{test.id}</span>
        <span className="shrink-0 text-muted-foreground">{test.duration_ms.toFixed(1)}ms</span>
        {target && (
          <button
            type="button"
            className="max-w-[45%] shrink-0 truncate rounded-md px-2 py-1 text-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            title={`open ${target.file} at line ${target.line}`}
            onClick={() => onJump(target.file, target.line)}
          >
            {target.file}:{target.line} →
          </button>
        )}
      </div>
      {failed && test.message && (
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-destructive/5 p-3 font-mono text-xs leading-5 text-destructive">
          {test.message}
        </pre>
      )}
    </div>
  )
}

function shortName(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

export default function Workspace() {
  const { slug = '' } = useParams()
  const navigate = useNavigate()
  const [challenge, setChallenge] = useState<ChallengeDetail | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [sideTab, setSideTab] = useState<'brief' | 'files' | 'search'>('brief')
  const [openPath, setOpenPath] = useState<string>('')
  const [openTabs, setOpenTabs] = useState<string[]>([])
  const [contents, setContents] = useState<Record<string, string>>({})
  const [dirty, setDirty] = useState<Set<string>>(new Set())
  const [savedFlash, setSavedFlash] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<RunResult | null>(null)
  const [outputOpen, setOutputOpen] = useState(false)
  const [timer, setTimer] = useState<TimerState | null>(null)
  const [rawOpen, setRawOpen] = useState(false)
  const [drawerTab, setDrawerTab] = useState<'results' | 'history'>('results')
  const [runs, setRuns] = useState<RunHistoryEntry[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runsError, setRunsError] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [newPath, setNewPath] = useState('')
  const [fileOpError, setFileOpError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchHits, setSearchHits] = useState<SearchHit[]>([])
  const [searching, setSearching] = useState(false)
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
  const skipUnsavedRef = useRef(false)

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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        setSideTab('search')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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
      setOpenPath(path)
      setOpenTabs((tabs) => (tabs.includes(path) ? tabs : [...tabs, path]))
      setSideTab((tab) => (tab === 'search' ? tab : 'files'))
      // On narrow layouts, opening a file should reveal the editor.
      setMobileSideOpen(false)
      if (contentsRef.current[path] === undefined) {
        const content = await api.getFile(slug, path, { signal })
        if (signal?.aborted) return
        setContents((c) => ({ ...c, [path]: content }))
      }
    },
    [slug],
  )

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const detail = await api.getChallenge(slug, { signal })
      if (signal?.aborted) return
      setChallenge(detail)
      // Solved challenges keep their frozen time; unsolved ones (re)start the clock.
      const t = loadTimer(slug)
      setTimer(detail.progress.status === 'solved' ? stopTimer(slug, t) : t)
      const first = selectInitialEditableFile(detail.files)
      if (first) await openFile(first.path, signal)
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
        setRuns(list)
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
    openFile(path).then(() => requestAnimationFrame(revealPending))
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
    setContents((c) => ({ ...c, [openPath]: value }))
    setDirty((d) => new Set(d).add(openPath))
  }

  async function saveAll() {
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
        return next
      })
      return
    }
    await Promise.all(paths.map((p) => api.saveFile(slug, p, contentsRef.current[p])))
    setDirty(new Set())
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
    const path = openPathRef.current
    if (!path || !dirtyRef.current.has(path)) return
    const meta = challenge?.files.find((f) => f.path === path)
    if (meta?.readonly) return
    await api.saveFile(slug, path, contentsRef.current[path] ?? '')
    setDirty((d) => {
      const next = new Set(d)
      next.delete(path)
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
    setSavedFlash(true)
    window.setTimeout(() => setSavedFlash(false), 1200)
  }
  useEffect(() => {
    saveCurrentRef.current = saveCurrent
  })

  async function runSearch(e?: React.FormEvent) {
    e?.preventDefault()
    const q = searchQuery.trim()
    if (!q) {
      setSearchHits([])
      return
    }
    setSearching(true)
    try {
      setSearchHits(await api.search(slug, q))
    } catch (err) {
      console.error(err)
      setSearchHits([])
    } finally {
      setSearching(false)
    }
  }

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
    setRunning(true)
    setOutputOpen(true)
    setDrawerTab('results')
    try {
      await saveAll()
      const sessionMs = timer ? elapsedMs(timer) : undefined
      const job = await api.startRun(slug, sessionMs)
      let offset = 0
      let streamedOutput = ''
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
          setRawOpen(true)
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
      // No structured results (timeout / collection crash) → raw log is the story.
      setRawOpen(r.tests.length === 0)
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
        output: `Run failed before pytest finished.\n\n${message}\n\nCheck that uvicorn is running on http://127.0.0.1:8000 and that you opened the app via http://localhost:5173 (Vite proxies /api there).`,
        output_truncated: false,
        tests: [],
        passed: 0,
        failed: 0,
        errors: 1,
        skipped: 0,
      })
      setRawOpen(true)
    } finally {
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
    setSearchHits([])
    setTimer(clearTimer(slug))
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
    setRawOpen(run.tests.length === 0)
    setDrawerTab('results')
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
    return <div className="py-32 text-center text-sm text-muted-foreground">Opening workspace…</div>

  const openFileMeta = challenge.files.find((f) => f.path === openPath)
  const solved = challenge.progress.status === 'solved'
  const alreadyOpen = solved || !!challenge.progress.spoiled

  async function handleSolutionNav(e: React.MouseEvent) {
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
      window.alert('Could not record spoil — try again.')
      return
    }
    if (dirty.size > 0) skipUnsavedRef.current = true
    navigate(`/c/${slug}/solution`)
  }

  return (
    <div className="flex h-svh min-w-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-card px-3 py-2 md:px-5">
        <Link to="/challenges" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
          ←
        </Link>
        <span className="min-w-0 truncate text-sm font-semibold">{challenge.title}</span>
        <span className="hidden rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground sm:inline-flex">
          {challenge.type}
        </span>
        <span className="hidden rounded-full border px-2.5 py-1 text-[11px] text-muted-foreground md:inline-flex">
          {challenge.difficulty}
        </span>
        <span
          className={cn(
            'rounded-full px-2.5 py-1 text-[11px] font-semibold',
            challenge.progress.status === 'solved' && 'bg-success/10 text-success',
            challenge.progress.status === 'attempted' && 'bg-warning/10 text-warning',
            challenge.progress.status === 'todo' && 'bg-muted text-muted-foreground',
          )}
        >
          {solved ? '● SOLVED' : challenge.progress.status === 'attempted' ? '◐ ATTEMPTED' : '○ TODO'}
        </span>
        {timer && <Timer minutes={challenge.minutes} state={timer} />}
        <div className="flex-1" />
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
        {savedFlash && <span className="text-xs font-semibold text-success">saved</span>}
        <Link
          to={`/c/${slug}/solution`}
          className={cn(buttonVariants({ variant: 'utility', size: 'sm' }), 'max-sm:min-h-11')}
          onClick={(e) => void handleSolutionNav(e)}
        >
          Solution
        </Link>
        <Button type="button" variant="primary" size="sm" className="px-4 max-sm:min-h-11" onClick={runTests} disabled={running}>
          {running ? 'Running…' : '▶ Run tests'}
        </Button>
      </header>

      {solved && (
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-success/20 bg-success/10 px-4 py-2 text-sm text-success md:px-5">
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

      <div className="relative grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside
          className={cn(
            'min-h-0 w-full flex-col overflow-hidden border-b bg-card lg:static lg:z-auto lg:flex lg:w-auto lg:border-r lg:border-b-0',
            mobileSideOpen ? 'absolute inset-0 z-30 flex' : 'hidden',
          )}
          id="ws-side-panel"
        >
          <div className="flex shrink-0 gap-1 border-b p-2" role="group" aria-label="Workspace panel">
            <button
              type="button"
              aria-pressed={sideTab === 'brief'}
              className={cn(
                'min-h-11 flex-1 rounded-md px-2 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:min-h-9',
                sideTab === 'brief' && 'bg-muted text-foreground',
              )}
              onClick={() => setSideTab('brief')}
            >
              Brief
            </button>
            <button
              type="button"
              aria-pressed={sideTab === 'files'}
              className={cn(
                'min-h-11 flex-1 rounded-md px-2 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:min-h-9',
                sideTab === 'files' && 'bg-muted text-foreground',
              )}
              onClick={() => setSideTab('files')}
            >
              Files
            </button>
            <button
              type="button"
              aria-pressed={sideTab === 'search'}
              className={cn(
                'min-h-11 flex-1 rounded-md px-2 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:min-h-9',
                sideTab === 'search' && 'bg-muted text-foreground',
              )}
              onClick={() => setSideTab('search')}
              title="Search in challenge (⌘⇧F)"
            >
              Search
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {sideTab === 'brief' ? (
              <div className="workspace-prose p-5">
                <div className="mb-5 flex flex-wrap gap-1.5">
                  <span className="rounded-full border px-2 py-1 text-[11px] text-muted-foreground">~{challenge.minutes} min</span>
                  <span className="rounded-full border px-2 py-1 text-[11px] text-muted-foreground">{challenge.language}</span>
                  <span className="rounded-full border px-2 py-1 text-[11px] text-muted-foreground">attempts: {challenge.progress.attempts}</span>
                </div>
                <ReactMarkdown>{challenge.brief}</ReactMarkdown>
              </div>
            ) : sideTab === 'search' ? (
              <div className="p-3">
                <form className="flex gap-2" onSubmit={(e) => void runSearch(e)}>
                  <input
                    className="min-h-10 min-w-0 flex-1 rounded-md border bg-background px-3 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/15"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="search in files…"
                    aria-label="search challenge files"
                    autoFocus
                  />
                  <Button type="submit" variant="utility" size="sm" disabled={searching || !searchQuery.trim()}>
                    {searching ? '…' : 'go'}
                  </Button>
                </form>
                <div className="mt-3 grid gap-1">
                  {searchHits.length === 0 ? (
                    <span className="px-2 py-6 text-center text-xs text-muted-foreground">
                      {searchQuery.trim() ? 'no matches' : 'type a query and press go'}
                    </span>
                  ) : (
                    searchHits.map((h, i) => (
                      <button
                        key={`${h.path}:${h.line}:${i}`}
                        type="button"
                        className="grid w-full gap-0.5 rounded-md px-2 py-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => jumpTo(h.path, h.line)}
                      >
                        <span className="truncate font-mono text-[11px] font-semibold text-primary">
                          {h.path}:{h.line}
                        </span>
                        <span className="truncate font-mono text-xs text-muted-foreground">{h.text.trim()}</span>
                      </button>
                    ))
                  )}
                </div>
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
                        'flex min-h-11 min-w-0 flex-1 items-center gap-2 px-3 text-left font-mono text-xs text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring lg:min-h-10',
                        f.path === openPath && 'bg-primary/8 text-foreground',
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

        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <div className="flex h-10 shrink-0 items-stretch overflow-x-auto border-b bg-card">
            {openTabs.length === 0 ? (
              <span className="flex items-center px-4 font-mono text-xs text-muted-foreground">select a file</span>
            ) : (
              openTabs.map((path) => (
                <div key={path} className={cn('flex shrink-0 items-center border-r', path === openPath && 'bg-muted')}>
                  <button
                    type="button"
                    className={cn(
                      'h-full max-w-48 truncate px-3 font-mono text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                      path === openPath && 'text-foreground',
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
                    className="extend-touch-target mr-1 size-7 rounded-md text-muted-foreground hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={`close ${path}`}
                    onClick={(e) => closeTab(path, e)}
                  >
                    ×
                  </button>
                </div>
              ))
            )}
          </div>
          {openFileMeta?.readonly && (
            <div className="shrink-0 border-b border-warning/20 bg-warning/10 px-4 py-1.5 text-center text-[11px] font-medium text-warning">
              read-only — tests are the spec, not the suspect
            </div>
          )}
          <div className="min-h-[180px] flex-1 bg-console">
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
            className={cn(
              'shrink-0 overflow-hidden border-t bg-card transition-[height] duration-200',
              outputOpen ? 'h-[40%] min-h-[180px]' : 'h-10',
            )}
            aria-label="Test output"
          >
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
                    : `${result.failed} failed · ${result.passed} passed${result.errors ? ` · ${result.errors} errors` : ''}`}
                </span>
              )}
              {running && <span className="ml-2 animate-spin text-muted-foreground">◜</span>}
            </div>
            {outputOpen &&
              (drawerTab === 'history' ? (
                <div className="h-[calc(100%_-_2.5rem)] overflow-auto">
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
                      />
                    ))
                  )}
                </div>
              ) : result && result.tests.length > 0 ? (
                <div className="h-[calc(100%_-_2.5rem)] overflow-auto">
                  {result.output_truncated && (
                    <div className="border-b border-warning/20 bg-warning/10 px-4 py-2 text-xs text-warning">
                      output truncated — showing the last 20,000 characters
                    </div>
                  )}
                  <div>
                    {result.tests.map((t) => (
                      <TestRow key={t.id} test={t} onJump={jumpTo} />
                    ))}
                  </div>
                  <button
                    type="button"
                    className="w-full border-y bg-muted/50 px-4 py-2 text-left font-mono text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                    onClick={() => setRawOpen((o) => !o)}
                  >
                    {rawOpen ? '▾' : '▸'} raw pytest output
                  </button>
                  {rawOpen && (
                    <pre className="m-0 max-h-64 overflow-auto bg-console p-4 font-mono text-xs leading-5 text-console-foreground">
                      {result.output.split('\n').map((l, i) => (
                        <OutputLine key={i} line={l} />
                      ))}
                    </pre>
                  )}
                </div>
              ) : (
                <div className="h-[calc(100%_-_2.5rem)] overflow-auto bg-console p-4 font-mono text-xs leading-5 text-console-foreground">
                  {result ? (
                    <>
                      {result.output_truncated && (
                        <div className="mb-3 rounded-md bg-console-warning/10 px-3 py-2 text-console-warning">
                          output truncated — showing the last 20,000 characters
                        </div>
                      )}
                      {result.output.split('\n').map((l, i) => (
                        <OutputLine key={i} line={l} />
                      ))}
                    </>
                  ) : (
                    <span className="text-console-muted">
                      {running ? 'running pytest in sandbox…' : 'hit ▶ Run tests to execute the suite'}
                    </span>
                  )}
                </div>
              ))}
          </section>
        </div>
      </div>
    </div>
  )
}
