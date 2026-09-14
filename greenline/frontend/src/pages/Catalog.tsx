import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  isAbortError,
  type ChallengeSummary,
  type ChallengeVariant,
  type PrepPath,
} from '../api'
import { LoadError } from '../components/LoadError'
import { PREP_TRACKS } from '../prepPaths'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const FOCUS_STORAGE_KEY = 'greenline-prep-focus'

type FocusId = PrepPath

function storedFocus(): FocusId | '' {
  try {
    const value = localStorage.getItem(FOCUS_STORAGE_KEY)
    return PREP_TRACKS.some((track) => track.id === value) ? (value as FocusId) : ''
  } catch {
    return ''
  }
}

function statusLabel(status: ChallengeSummary['progress']['status']) {
  if (status === 'solved') return '● SOLVED'
  if (status === 'attempted') return '◐ ATTEMPTED'
  return '○ TODO'
}

function variantsFor(challenge: ChallengeSummary): ChallengeVariant[] {
  return challenge.variants ?? [
    {
      id: challenge.variant ?? 'default',
      language: challenge.language,
      slug: challenge.slug,
      progress: challenge.progress,
    },
  ]
}

function defaultVariant(challenge: ChallengeSummary): ChallengeVariant {
  const variants = variantsFor(challenge)
  return (
    variants.find((variant) => variant.language.toLowerCase() === 'python') ??
    variants.find((variant) => variant.slug === challenge.slug) ??
    variants[0]
  )
}

export default function Catalog() {
  const [challenges, setChallenges] = useState<ChallengeSummary[] | null>(null)
  const [error, setError] = useState(false)
  const [filter, setFilter] = useState('All')
  const [focus, setFocus] = useState<FocusId | ''>(storedFocus)
  const [focusSaving, setFocusSaving] = useState(false)
  const [focusError, setFocusError] = useState(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [items, preferences] = await Promise.all([
        api.listChallenges({ signal }),
        api.getPreferences({ signal }),
      ])
      if (signal?.aborted) return
      setChallenges(items)
      const cached = storedFocus()
      const synced = preferences.prep_path ?? cached
      setFocus(synced)
      if (!preferences.prep_path && cached) {
        void api.setPrepPath(cached).catch(() => setFocusError(true))
      }
      void api.recordVisit().catch(() => undefined)
    } catch (err) {
      if (!isAbortError(err)) setError(true)
    }
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    // oxlint-disable-next-line react/set-state-in-effect -- the effect synchronizes API state.
    void load(ac.signal)
    return () => ac.abort()
  }, [load])

  const types = useMemo(
    () => ['All', ...new Set((challenges ?? []).map((c) => c.type))],
    [challenges],
  )
  const shown = (challenges ?? []).filter((c) => filter === 'All' || c.type === filter)
  const selectedTrack = PREP_TRACKS.find((track) => track.id === focus)
  const trackChallenges = selectedTrack
    ? selectedTrack.slugs.flatMap((slug) => {
        const challenge = challenges?.find((item) => item.slug === slug)
        return challenge ? [challenge] : []
      })
    : []
  const solvedInTrack = trackChallenges.filter((c) => c.progress.status === 'solved').length
  const recommended =
    trackChallenges.find((c) => c.progress.status === 'attempted') ??
    trackChallenges.find((c) => c.progress.status === 'todo')

  async function chooseFocus(value: string) {
    const next = PREP_TRACKS.some((track) => track.id === value) ? (value as FocusId) : ''
    if (!next || next === focus) return
    const previous = focus
    setFocus(next)
    setFocusSaving(true)
    setFocusError(false)
    try {
      await api.setPrepPath(next)
    } catch {
      setFocus(previous)
      setFocusError(true)
      return
    } finally {
      setFocusSaving(false)
    }
    try {
      localStorage.setItem(FOCUS_STORAGE_KEY, next)
    } catch {
      // The account-backed preference remains authoritative.
    }
  }

  if (error) {
    return (
      <LoadError
        onRetry={() => {
          setError(false)
          setChallenges(null)
          void load()
        }}
      />
    )
  }
  if (!challenges)
    return <div className="py-32 text-center text-sm text-muted-foreground">Loading challenges…</div>

  return (
    <main className="mx-auto max-w-[1080px] px-6 py-16 md:px-10 md:py-24">
      <h1 className="text-[clamp(2.5rem,5vw,3.375rem)] font-bold leading-none tracking-[-0.035em]">Challenges</h1>
      <p className="mt-4 text-muted-foreground">
        {challenges.length} challenges · {challenges.filter((c) => c.progress.status === 'solved').length} solved
      </p>

      <fieldset className="mt-10">
        <legend className="text-xl font-bold tracking-[-0.015em]">Choose a prep path</legend>
        <p className="mt-1 text-sm text-muted-foreground">
          Pick a direction. You can switch whenever you want.
        </p>
        {focusError && (
          <p className="mt-2 text-sm text-destructive" role="alert">
            Could not save your prep path. Try again.
          </p>
        )}
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PREP_TRACKS.map((track) => {
            const selected = focus === track.id
            return (
              <label
                key={track.id}
                className={cn(
                  'relative cursor-pointer rounded-xl border bg-card p-4 transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:shadow-soft focus-within:ring-2 focus-within:ring-ring',
                  selected && 'border-primary shadow-soft',
                )}
              >
                <input
                  type="radio"
                  className="sr-only"
                  name="prep-focus"
                  value={track.id}
                  checked={selected}
                  disabled={focusSaving}
                  onChange={(event) => void chooseFocus(event.target.value)}
                />
                <span className={cn('mb-5 block size-2.5 rounded-full', track.accent)} aria-hidden="true" />
                <span className="block font-semibold leading-5">{track.name}</span>
                <span className="mt-2 block text-sm leading-5 text-muted-foreground">
                  {track.description}
                </span>
                <span className="mt-4 block text-xs font-medium text-muted-foreground">
                  {track.cadence}
                </span>
                {selected && (
                  <span className="absolute right-3 top-3 text-xs font-semibold text-primary">
                    Selected
                  </span>
                )}
              </label>
            )
          })}
        </div>
      </fieldset>

      {selectedTrack && (
        recommended ? (
          <Link
            to={`/c/${defaultVariant(recommended).slug}`}
            aria-label={`${recommended.progress.status === 'attempted' ? 'Continue' : 'Recommended next'}: ${recommended.title}`}
            className="mt-5 block overflow-hidden rounded-xl border bg-card shadow-soft transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-black/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <span className="flex flex-wrap items-center gap-5 px-5 py-5 md:px-6">
              <span className="mr-auto min-w-[220px]">
                <span className="block text-xs font-semibold text-primary">
                  {recommended.progress.status === 'attempted' ? 'Continue' : 'Up next'}
                </span>
                <span className="mt-1 block text-xl font-bold tracking-[-0.015em]">
                  {recommended.title}
                </span>
                <span className="mt-1 block max-w-2xl text-sm leading-5 text-muted-foreground">
                  {recommended.blurb}
                </span>
              </span>
              <span className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>{variantsFor(recommended).map((variant) => variant.language).join(' / ')}</span>
                <span aria-hidden="true">·</span>
                <span>{recommended.difficulty}</span>
                <span aria-hidden="true">·</span>
                <span>~{recommended.minutes} min</span>
              </span>
              <span className="grid size-10 place-items-center rounded-full bg-primary text-lg text-primary-foreground" aria-hidden="true">
                →
              </span>
            </span>
            <span className="block border-t bg-background/60 px-5 py-3 md:px-6">
              <span className="flex items-center gap-3 text-xs text-muted-foreground">
                <span>{selectedTrack.name}</span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <span
                    className="block h-full rounded-full bg-primary"
                    style={{
                      width: `${trackChallenges.length ? (solvedInTrack / trackChallenges.length) * 100 : 0}%`,
                    }}
                  />
                </span>
                <span>{solvedInTrack} of {trackChallenges.length} completed</span>
              </span>
            </span>
          </Link>
        ) : (
          <div className="mt-5 rounded-xl border border-success/30 bg-success/10 px-5 py-4">
            <span className="font-semibold text-success">Track complete</span>
            <span className="ml-2 text-sm text-muted-foreground">
              {solvedInTrack} of {trackChallenges.length} challenges completed
            </span>
          </div>
        )
      )}

      <div className="mt-12">
        <h2 className="text-xl font-bold tracking-[-0.015em]">Browse all challenges</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {types.map((t) => (
            <Button
              key={t}
              type="button"
              variant={filter === t ? 'primary' : 'utility'}
              size="sm"
              className="rounded-full px-4"
              onClick={() => setFilter(t)}
            >
              {t}
            </Button>
          ))}
        </div>
      </div>

      <div className="mt-8 grid gap-3">
        {shown.map((c) => {
          const variants = variantsFor(c)
          return (
            <article
              className="rounded-lg border bg-card p-5 transition-[border-color,box-shadow] hover:border-black/20 hover:shadow-soft"
              key={c.concept_slug ?? c.slug}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={`/c/${defaultVariant(c).slug}`}
                  className="mr-auto min-w-[220px] text-lg font-semibold tracking-[-0.01em] hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {c.title}
                </Link>
                <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{c.type}</span>
                <span className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground">{c.difficulty}</span>
                {variants.length === 1 && (
                  <span className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground">{c.language}</span>
                )}
                <span className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground">~{c.minutes} min</span>
                <span className="flex gap-1.5">
                  <span
                    className={cn(
                      'rounded-full px-2.5 py-1 text-[11px] font-semibold',
                      c.progress.status === 'solved' && 'bg-success/10 text-success',
                      c.progress.status === 'attempted' && 'bg-warning/10 text-warning',
                      c.progress.status === 'todo' && 'bg-muted text-muted-foreground',
                    )}
                  >
                    {statusLabel(c.progress.status)}
                  </span>
                  {c.progress.spoiled && (
                    <span className="rounded-full bg-destructive/10 px-2.5 py-1 text-[11px] font-semibold text-destructive">SPOILED</span>
                  )}
                </span>
              </div>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{c.blurb}</p>
              {variants.length > 1 && (
                <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-4">
                  <span className="mr-1 text-xs font-medium text-muted-foreground">Solve in</span>
                  {variants.map((variant) => (
                    <span
                      key={variant.id}
                      className="inline-flex min-h-8 items-center rounded-full border bg-muted/30 px-3 text-xs font-semibold text-muted-foreground"
                    >
                      {variant.language}
                    </span>
                  ))}
                </div>
              )}
            </article>
          )
        })}
      </div>
    </main>
  )
}
