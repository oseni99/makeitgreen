import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DiffEditor } from '@monaco-editor/react'
import ReactMarkdown from 'react-markdown'
import { api, isAbortError, isNotFoundError, type Solution as SolutionData } from '../api'
import { LoadError } from '../components/LoadError'
import { defineGreenlineTheme } from '../monacoTheme'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'

type FileView = 'diff' | 'left' | 'right'
type CompareMode = 'broken' | 'yours'

function editorHeight(fixed: string, original: string): number {
  const lines = Math.max(fixed.split('\n').length, original.split('\n').length)
  return Math.min(520, Math.max(180, lines * 19 + 40))
}

function FileBlock({
  path,
  fixed,
  original,
  userContent,
  compareMode,
}: {
  path: string
  fixed: string
  original: string
  userContent: string | null
  compareMode: CompareMode
}) {
  const [view, setView] = useState<FileView>('diff')
  const missingYours = compareMode === 'yours' && userContent === null
  const left = compareMode === 'yours' ? (userContent ?? '') : original
  const leftLabel = compareMode === 'yours' ? 'yours' : 'broken'
  const height = editorHeight(fixed, left)

  const leftSource =
    compareMode === 'yours'
      ? missingYours
        ? '(not in your workspace)'
        : left
      : original || '(file did not exist in original)'

  return (
    <section className="mt-10 overflow-hidden rounded-lg border bg-card">
      <div className="flex flex-wrap items-center gap-3 border-b bg-muted/60 px-4 py-3 text-sm">
        <span className="font-mono font-semibold text-foreground">{path}</span>
        {missingYours && <span className="text-xs text-muted-foreground">not in your workspace</span>}
        <div className="ml-auto flex gap-1">
          {([
            ['diff', 'diff'],
            ['left', leftLabel],
            ['right', 'fixed'],
          ] as const).map(([key, label]) => (
            <Button
              key={key}
              type="button"
              variant={view === key ? 'primary' : 'ghost'}
              size="sm"
              className="min-h-8 rounded-md px-3 text-xs"
              onClick={() => setView(key)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>
      {view === 'diff' ? (
        <div className="bg-console" style={{ height }}>
          <DiffEditor
            key={compareMode}
            original={left}
            modified={fixed}
            language="python"
            beforeMount={defineGreenlineTheme}
            theme="greenline"
            options={{
              readOnly: true,
              renderSideBySide: true,
              fontSize: 12.5,
              fontFamily: "'IBM Plex Mono', monospace",
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              renderOverviewRuler: false,
              hideUnchangedRegions: { enabled: true },
            }}
          />
        </div>
      ) : (
        <pre className="m-0 max-h-[480px] overflow-auto bg-console p-5 font-mono text-[12.5px] leading-7 text-console-foreground">
          {view === 'right' ? fixed : leftSource}
        </pre>
      )}
    </section>
  )
}

export default function Solution() {
  const { slug = '' } = useParams()
  const [solution, setSolution] = useState<SolutionData | null>(null)
  const [userFiles, setUserFiles] = useState<Record<string, string | null>>({})
  const [error, setError] = useState(false)
  const [gated, setGated] = useState(false)
  const [spoiling, setSpoiling] = useState(false)
  const [compareMode, setCompareMode] = useState<CompareMode>('broken')

  const loadUserFiles = useCallback(
    async (sol: SolutionData, signal?: AbortSignal) => {
      const entries = await Promise.all(
        sol.files.map(async (f) => {
          try {
            const content = await api.getFile(slug, f.path, { signal })
            return [f.path, content] as const
          } catch (err) {
            if (isAbortError(err)) throw err
            if (isNotFoundError(err)) return [f.path, null] as const
            throw err
          }
        }),
      )
      if (signal?.aborted) return
      setUserFiles(Object.fromEntries(entries))
    },
    [slug],
  )

  const reveal = useCallback(
    async (signal?: AbortSignal) => {
      const sol = await api.getSolution(slug, { signal })
      await loadUserFiles(sol, signal)
      if (signal?.aborted) return
      setSolution(sol)
    },
    [slug, loadUserFiles],
  )

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const detail = await api.getChallenge(slug, { signal })
        if (signal?.aborted) return
        if (detail.progress.status !== 'solved' && !detail.progress.spoiled) {
          setGated(true)
          return
        }
        setGated(false)
        await reveal(signal)
      } catch (err) {
        if (!isAbortError(err)) setError(true)
      }
    },
    [slug, reveal],
  )

  useEffect(() => {
    const ac = new AbortController()
    void Promise.resolve().then(() => load(ac.signal))
    return () => ac.abort()
  }, [load])

  async function confirmSpoil() {
    setSpoiling(true)
    try {
      await api.spoil(slug)
    } catch {
      setSpoiling(false)
      window.alert('Could not record spoil — try again.')
      return
    }
    try {
      await reveal()
      setGated(false)
    } catch {
      setGated(false)
      setError(true)
    } finally {
      setSpoiling(false)
    }
  }

  if (error) {
    return (
      <LoadError
        onRetry={() => {
          setError(false)
          setSolution(null)
          setGated(false)
          void load()
        }}
      />
    )
  }
  if (gated) {
    return (
      <main className="mx-auto max-w-[920px] px-6 py-14 md:px-10 md:py-20">
        <Link to={`/c/${slug}`} className="text-sm text-muted-foreground hover:text-foreground">
          ← back to workspace
        </Link>
        <h1 className="mt-6 text-[clamp(2.5rem,5vw,3.375rem)] font-bold leading-none tracking-[-0.035em]">Reference solution</h1>
        <div className="mt-8 rounded-lg border bg-card p-7 shadow-soft">
          <p className="mb-5 text-muted-foreground">Viewing the solution marks this challenge as spoiled — attempt it first?</p>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="primary"
              onClick={() => void confirmSpoil()}
              disabled={spoiling}
            >
              {spoiling ? 'Recording…' : 'Confirm'}
            </Button>
            <Link to={`/c/${slug}`} className={buttonVariants({ variant: 'secondary' })}>
              Back
            </Link>
          </div>
        </div>
      </main>
    )
  }
  if (!solution)
    return <div className="py-32 text-center text-sm text-muted-foreground">Loading solution…</div>

  return (
    <main className="mx-auto max-w-[920px] px-6 py-14 md:px-10 md:py-20">
      <Link to={`/c/${slug}`} className="text-sm text-muted-foreground hover:text-foreground">
        ← back to workspace
      </Link>
      <div className="mt-6 flex flex-wrap items-end justify-between gap-5">
        <h1 className="text-[clamp(2.5rem,5vw,3.375rem)] font-bold leading-none tracking-[-0.035em]">Reference solution</h1>
        <div className="flex gap-2">
          <Button
            type="button"
            variant={compareMode === 'broken' ? 'primary' : 'utility'}
            size="sm"
            className="rounded-full px-4"
            onClick={() => setCompareMode('broken')}
          >
            broken → fixed
          </Button>
          <Button
            type="button"
            variant={compareMode === 'yours' ? 'primary' : 'utility'}
            size="sm"
            className="rounded-full px-4"
            onClick={() => setCompareMode('yours')}
          >
            yours → fixed
          </Button>
        </div>
      </div>
      <div className="prose-greenline mt-12">
        <ReactMarkdown>{solution.writeup}</ReactMarkdown>
      </div>
      {solution.files.map((f) => (
        <FileBlock
          key={f.path}
          path={f.path}
          fixed={f.content}
          original={f.original}
          userContent={Object.hasOwn(userFiles, f.path) ? userFiles[f.path] : null}
          compareMode={compareMode}
        />
      ))}
    </main>
  )
}
