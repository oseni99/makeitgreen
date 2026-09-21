import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DiffEditor } from '@monaco-editor/react'
import ReactMarkdown from 'react-markdown'
import {
  api,
  isAbortError,
  type ChallengeDetail,
  type Debrief,
  type Solution as SolutionData,
} from '../api'
import { LoadError } from '../components/LoadError'
import { PageLoading } from '../components/PageLoading'
import { useMonacoLanguage } from '../monacoLanguages'
import { defineGreenlineTheme } from '../monacoTheme'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'

interface ChangeCount {
  additions: number
  deletions: number
}

function withoutLeadingTitle(markdown: string): string {
  return markdown.replace(/^\s*#\s+[^\n]+\n+/, '')
}

function lineChanges(before: string, after: string): ChangeCount {
  const beforeLines = before === '' ? [] : before.split('\n')
  const afterLines = after === '' ? [] : after.split('\n')
  let previous = new Uint32Array(afterLines.length + 1)

  for (const beforeLine of beforeLines) {
    const current = new Uint32Array(afterLines.length + 1)
    for (let index = 1; index <= afterLines.length; index += 1) {
      current[index] = beforeLine === afterLines[index - 1]
        ? previous[index - 1] + 1
        : Math.max(previous[index], current[index - 1])
    }
    previous = current
  }

  const unchanged = previous[afterLines.length]
  return {
    additions: afterLines.length - unchanged,
    deletions: beforeLines.length - unchanged,
  }
}

function editorHeight(fixed: string, original: string): number {
  const lines = Math.max(fixed.split('\n').length, original.split('\n').length)
  return Math.min(520, Math.max(180, lines * 19 + 40))
}

function editorLanguage(path: string): string {
  if (path.endsWith('.js') || path.endsWith('.mjs') || path.endsWith('.cjs')) return 'javascript'
  if (path.endsWith('.ts') || path.endsWith('.tsx')) return 'typescript'
  if (path.endsWith('.json')) return 'json'
  if (path.endsWith('.md')) return 'markdown'
  return 'python'
}

function FileBlock({
  path,
  fixed,
  original,
  changeCount,
  defaultExpanded,
}: {
  path: string
  fixed: string
  original: string
  changeCount: ChangeCount
  defaultExpanded: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const height = editorHeight(fixed, original)
  const language = useMonacoLanguage(editorLanguage(path))

  return (
    <section className="mt-3 overflow-hidden rounded-lg border bg-card">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
        <span className="min-w-0 truncate font-mono font-semibold text-foreground">{path}</span>
        <span className="text-xs font-semibold text-success">+{changeCount.additions}</span>
        <span className="text-xs font-semibold text-destructive">−{changeCount.deletions}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto min-h-8 px-2.5 text-xs text-muted-foreground"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'collapse' : 'expand'}
        </Button>
      </div>
      {expanded && (
        <div>
          <div className="grid grid-cols-2 border-y bg-muted/60 px-4 py-2.5 text-xs font-semibold text-muted-foreground">
            <span>Starter code</span>
            <span className="pl-3">Official solution</span>
          </div>
          {language ? (
            <div className="bg-console" style={{ height }}>
              <DiffEditor
                original={original}
                modified={fixed}
                language={language}
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
            <div
              className="grid bg-console font-mono text-xs text-console-muted"
              role="status"
              style={{ height }}
            >
              <span className="place-self-center">Preparing diff…</span>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function SolutionHeader({
  challenge,
  slug,
}: {
  challenge: ChallengeDetail | null
  slug: string
}) {
  const variants = challenge?.variants?.length
    ? challenge.variants
    : challenge
      ? [{ language: challenge.language, slug: challenge.slug }]
      : []

  return (
    <header>
      <Link to={`/c/${slug}`} className="text-sm text-muted-foreground hover:text-foreground">
        ← back to workspace
      </Link>
      <h1 className="mt-5 text-[clamp(2rem,5vw,2.5rem)] font-bold leading-[1.1] tracking-[-0.025em]">
        {challenge?.title ?? slug} <span className="text-muted-foreground">— official fix</span>
      </h1>
      {variants.length > 1 && (
        <nav className="mt-4 flex flex-wrap gap-2" aria-label="Solution language">
          {variants.map((variant) => {
            const selected = variant.slug === slug
            return (
              <Link
                key={variant.slug}
                to={`/c/${variant.slug}/solution`}
                aria-current={selected ? 'page' : undefined}
                className={buttonVariants({
                  variant: selected ? 'primary' : 'utility',
                  size: 'sm',
                })}
              >
                {variant.language}
              </Link>
            )
          })}
        </nav>
      )}
      <p className="mt-4 max-w-2xl text-[15px] leading-6 text-muted-foreground">
        Use this to compare your approach after attempting the problem.
      </p>
    </header>
  )
}

function DebriefCard({ slug, initial }: { slug: string; initial: Debrief | null }) {
  const [rootCause, setRootCause] = useState(initial?.root_cause ?? '')
  const [fixReasoning, setFixReasoning] = useState(initial?.fix_reasoning ?? '')
  const [tradeoff, setTradeoff] = useState(initial?.tradeoff ?? '')
  const [useful, setUseful] = useState<boolean | null>(initial?.useful ?? null)
  const [feedback, setFeedback] = useState(initial?.feedback ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(Boolean(initial))
  const [error, setError] = useState(false)
  const [expanded, setExpanded] = useState(false)

  function changed() {
    setSaved(false)
    setError(false)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (useful === null) {
      setError(true)
      return
    }
    setSaving(true)
    setError(false)
    try {
      await api.saveDebrief(slug, {
        root_cause: rootCause.trim(),
        fix_reasoning: fixReasoning.trim(),
        tradeoff: tradeoff.trim(),
        useful,
        feedback: feedback.trim(),
      })
      setSaved(true)
    } catch {
      setError(true)
    } finally {
      setSaving(false)
    }
  }

  const fieldClass =
    'mt-2 min-h-[76px] w-full resize-y rounded-md border bg-background px-3 py-2 text-sm leading-6 outline-none transition-shadow placeholder:text-muted-foreground focus:ring-2 focus:ring-ring'

  return (
    <section className="mt-12 border-t pt-8" aria-labelledby="reflection-heading">
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <h2 id="reflection-heading" className="text-xl font-bold tracking-[-0.015em]">
            Reflection
          </h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Capture how you would explain the repair in an interview.
          </p>
        </div>
        <Button
          type="button"
          variant="utility"
          size="sm"
          className="ml-auto"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Hide reflection' : initial ? 'Review reflection' : 'Add reflection'}
        </Button>
      </div>

      {expanded && (
        <form className="mt-7 grid gap-6" onSubmit={(event) => void submit(event)}>
          <label className="text-sm font-semibold">
            What was the root cause?
            <textarea
              className={fieldClass}
              value={rootCause}
              maxLength={1000}
              required
              onChange={(event) => {
                setRootCause(event.target.value)
                changed()
              }}
            />
          </label>
          <label className="text-sm font-semibold">
            Why does the fix work?
            <textarea
              className={fieldClass}
              value={fixReasoning}
              maxLength={1000}
              required
              onChange={(event) => {
                setFixReasoning(event.target.value)
                changed()
              }}
            />
          </label>
          <label className="text-sm font-semibold">
            What tradeoff did it introduce?
            <textarea
              className={fieldClass}
              value={tradeoff}
              maxLength={1000}
              required
              onChange={(event) => {
                setTradeoff(event.target.value)
                changed()
              }}
            />
          </label>

          <div className="border-t pt-6">
            <p className="text-sm font-semibold">Was this challenge useful?</p>
            <div className="mt-3 flex gap-2">
              <Button
                type="button"
                variant={useful === true ? 'primary' : 'utility'}
                size="sm"
                aria-pressed={useful === true}
                onClick={() => {
                  setUseful(true)
                  changed()
                }}
              >
                Yes
              </Button>
              <Button
                type="button"
                variant={useful === false ? 'primary' : 'utility'}
                size="sm"
                aria-pressed={useful === false}
                onClick={() => {
                  setUseful(false)
                  changed()
                }}
              >
                Not really
              </Button>
            </div>
            <label className="mt-5 block text-sm font-semibold">
              Anything we should improve?{' '}
              <span className="font-normal text-muted-foreground">Optional</span>
              <textarea
                className={fieldClass}
                value={feedback}
                maxLength={1000}
                onChange={(event) => {
                  setFeedback(event.target.value)
                  changed()
                }}
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? 'Saving…' : initial ? 'Update debrief' : 'Save debrief'}
            </Button>
            {saved && <span className="text-sm font-medium text-success">Saved</span>}
            {error && (
              <span className="text-sm text-destructive" role="alert">
                {useful === null ? 'Choose whether this was useful.' : 'Could not save. Try again.'}
              </span>
            )}
          </div>
        </form>
      )}
    </section>
  )
}

export default function Solution() {
  const { slug = '' } = useParams()
  const [challenge, setChallenge] = useState<ChallengeDetail | null>(null)
  const [solution, setSolution] = useState<SolutionData | null>(null)
  const [error, setError] = useState(false)
  const [gated, setGated] = useState(false)
  const [spoiling, setSpoiling] = useState(false)
  const [spoilError, setSpoilError] = useState('')
  const [solved, setSolved] = useState(false)
  const [debrief, setDebrief] = useState<Debrief | null>(null)
  const [debriefLoaded, setDebriefLoaded] = useState(false)

  const reveal = useCallback(
    async (signal?: AbortSignal) => {
      const sol = await api.getSolution(slug, { signal })
      if (signal?.aborted) return
      setSolution(sol)
    },
    [slug],
  )

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const detail = await api.getChallenge(slug, { signal })
        if (signal?.aborted) return
        setChallenge(detail)
        const challengeSolved = detail.progress.status === 'solved'
        setSolved(challengeSolved)
        if (detail.progress.status !== 'solved' && !detail.progress.spoiled) {
          setGated(true)
          return
        }
        setGated(false)
        if (challengeSolved) {
          const [, savedDebrief] = await Promise.all([
            reveal(signal),
            api.getDebrief(slug, { signal }),
          ])
          if (signal?.aborted) return
          setDebrief(savedDebrief)
          setDebriefLoaded(true)
        } else {
          await reveal(signal)
        }
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
    setSpoilError('')
    try {
      await api.spoil(slug)
    } catch {
      setSpoiling(false)
      setSpoilError('Could not unlock the solution. Your progress was not changed. Try again.')
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
      <main className="mx-auto max-w-[1180px] px-6 py-12 md:px-10 md:py-16">
        <SolutionHeader challenge={challenge} slug={slug} />
        <div className="mt-8 rounded-lg border bg-card p-7">
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
          {spoilError && (
            <p className="mt-4 text-sm text-destructive" role="alert">
              {spoilError}
            </p>
          )}
        </div>
      </main>
    )
  }
  if (!solution) return <PageLoading label="Loading solution…" />

  const fileChanges = solution.files.map((file) => ({
    ...file,
    changeCount: lineChanges(file.original, file.content),
  }))
  const additions = fileChanges.reduce((total, file) => total + file.changeCount.additions, 0)
  const deletions = fileChanges.reduce((total, file) => total + file.changeCount.deletions, 0)

  return (
    <main className="mx-auto max-w-[1180px] px-6 py-12 md:px-10 md:py-16">
      <SolutionHeader challenge={challenge} slug={slug} />

      <section className="mt-10 max-w-[820px]" aria-labelledby="solution-walkthrough-heading">
        <h2
          id="solution-walkthrough-heading"
          className="text-xs font-semibold uppercase tracking-[0.0078rem] text-muted-foreground"
        >
          Solution walkthrough
        </h2>
        <div className="prose-greenline mt-4">
          <ReactMarkdown>{withoutLeadingTitle(solution.writeup)}</ReactMarkdown>
        </div>
      </section>

      <section className="mt-12" aria-labelledby="solution-fix-heading">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b pb-4">
          <h2 id="solution-fix-heading" className="text-2xl font-bold tracking-[-0.02em]">
            The fix
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-muted-foreground">
              {fileChanges.length} {fileChanges.length === 1 ? 'file' : 'files'} changed
            </span>
            <span className="text-sm font-semibold text-success">+{additions}</span>
            <span className="text-sm font-semibold text-destructive">−{deletions}</span>
          </div>
        </div>

        {fileChanges.map((file, index) => (
          <FileBlock
            key={file.path}
            path={file.path}
            fixed={file.content}
            original={file.original}
            changeCount={file.changeCount}
            defaultExpanded={index === 0}
          />
        ))}
      </section>

      <div className="max-w-[820px]">
        {solved && debriefLoaded && <DebriefCard slug={slug} initial={debrief} />}
      </div>
    </main>
  )
}
