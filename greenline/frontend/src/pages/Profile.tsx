import { LogOut } from 'lucide-react'
import { useClerk, useUser } from '@clerk/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import {
  api,
  isAbortError,
  type ChallengeSummary,
  type LearnerPreferences,
  type SolveActivity,
} from '../api'
import { LoadError } from '../components/LoadError'
import { PREP_PATH_NAMES, PREP_TRACKS } from '../prepPaths'
import { buttonVariants } from '@/components/ui/button-variants'
import { Button } from '@/components/ui/button'

function continueSlug(challenge: ChallengeSummary): string {
  const variants = challenge.variants ?? []
  return (
    variants.find((variant) => variant.progress.status === 'attempted')?.slug ??
    variants.find((variant) => variant.progress.status === 'todo')?.slug ??
    challenge.slug
  )
}

function dayKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function activityDays(activity: SolveActivity[], today = new Date()) {
  const counts = new Map<string, number>()
  for (const solve of activity) {
    const solvedAt = new Date(solve.solved_at)
    if (Number.isNaN(solvedAt.getTime())) continue
    const key = dayKey(solvedAt)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }

  const localToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const currentWeekStart = new Date(localToday)
  currentWeekStart.setDate(currentWeekStart.getDate() - currentWeekStart.getDay())
  const firstDay = new Date(currentWeekStart)
  firstDay.setDate(firstDay.getDate() - 25 * 7)

  return Array.from({ length: 26 * 7 }, (_, index) => {
    const date = new Date(firstDay)
    date.setDate(date.getDate() + index)
    return {
      date,
      count: counts.get(dayKey(date)) ?? 0,
      future: date > localToday,
    }
  })
}

function ConfiguredProfile() {
  const { isLoaded, isSignedIn, user } = useUser()
  const { signOut } = useClerk()
  const [challenges, setChallenges] = useState<ChallengeSummary[] | null>(null)
  const [preferences, setPreferences] = useState<LearnerPreferences | null>(null)
  const [activity, setActivity] = useState<SolveActivity[] | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [items, learnerPreferences, solveActivity] = await Promise.all([
        api.listChallenges({ signal }),
        api.getPreferences({ signal }),
        api.getSolveActivity({ signal }),
      ])
      if (signal?.aborted) return
      setChallenges(items)
      setPreferences(learnerPreferences)
      setActivity(solveActivity)
    } catch (err) {
      if (!isAbortError(err)) setError(true)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    // oxlint-disable-next-line react/set-state-in-effect -- synchronize remote profile state.
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const progress = useMemo(() => {
    const items = challenges ?? []
    const solved = items.filter((challenge) => challenge.progress.status === 'solved').length
    const attempted = items.filter((challenge) => challenge.progress.status === 'attempted').length
    return {
      solved,
      attempted,
      remaining: Math.max(0, items.length - solved - attempted),
    }
  }, [challenges])

  if (error) {
    return (
      <LoadError
        onRetry={() => {
          setError(false)
          setChallenges(null)
          setPreferences(null)
          setActivity(null)
          void load()
        }}
      />
    )
  }
  if (!isLoaded || !challenges || !preferences || !activity) {
    return <div className="py-32 text-center text-sm text-muted-foreground">Loading profile…</div>
  }
  if (!isSignedIn || !user) return <Navigate to="/sign-in" replace />

  const name = user.fullName ?? user.firstName ?? 'Your profile'
  const email = user.primaryEmailAddress?.emailAddress ?? ''
  const prepPath = preferences.prep_path
  const selectedTrack = PREP_TRACKS.find((track) => track.id === prepPath)
  const recommendedChallenges = selectedTrack
    ? selectedTrack.slugs.flatMap((slug) => {
        const challenge = challenges.find((item) => item.slug === slug)
        return challenge ? [challenge] : []
      })
    : challenges
  const next =
    recommendedChallenges.find((challenge) => challenge.progress.status === 'attempted') ??
    recommendedChallenges.find((challenge) => challenge.progress.status === 'todo')
  const days = activityDays(activity)

  return (
    <main className="mx-auto max-w-[920px] px-6 py-14 md:px-10 md:py-20">
      <div className="flex flex-wrap items-center gap-4">
        <img className="size-16 rounded-full object-cover" src={user.imageUrl} alt="" />
        <div className="min-w-0">
          <h1 className="truncate text-[2.5rem] font-bold leading-[1.1] tracking-[-0.025em]">{name}</h1>
          {email && <p className="mt-1 truncate text-sm text-muted-foreground">{email}</p>}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto text-destructive"
          onClick={() => void signOut({ redirectUrl: '/' })}
        >
          <LogOut className="size-4" aria-hidden="true" />
          Sign out
        </Button>
      </div>

      <section className="mt-12" aria-labelledby="progress-heading">
        <h2
          id="progress-heading"
          className="text-[1.625rem] font-bold leading-[1.23] tracking-[-0.039rem]"
        >
          Progress
        </h2>
        <div className="mt-3 rounded-lg border bg-card p-5">
          <div className="mb-3 flex items-baseline justify-between gap-4">
            <p className="text-sm font-semibold">Solve activity</p>
            <p className="text-xs text-muted-foreground">Last 6 months</p>
          </div>
          <div
            className="grid grid-flow-col grid-cols-[repeat(26,0.75rem)] grid-rows-7 justify-between gap-y-1 overflow-x-auto pb-1 sm:grid-cols-[repeat(26,0.875rem)]"
            role="group"
            aria-label="Daily solve activity"
          >
            {days.map(({ date, count, future }) => {
              const label = date.toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })
              const solveLabel = count === 1 ? '1 challenge solved' : `${count} challenges solved`
              return (
                <span
                  key={dayKey(date)}
                  className={`size-3 rounded-[0.1875rem] border sm:size-3.5 ${
                    future
                      ? 'border-transparent bg-transparent'
                      : count >= 3
                        ? 'border-success bg-success'
                        : count === 2
                          ? 'border-success/60 bg-success/60'
                          : count === 1
                            ? 'border-success/30 bg-success/30'
                            : 'border-border bg-muted'
                  }`}
                  aria-label={`${label}: ${future ? 'Future date' : solveLabel}`}
                  title={`${label} — ${future ? 'Future date' : solveLabel}`}
                />
              )
            })}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t pt-3 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">
              {progress.solved} solved · {progress.attempted} in progress · {progress.remaining} remaining
            </span>
            <span className="ml-auto flex items-center gap-1.5" aria-label="Activity intensity legend">
              <span>Less</span>
              <span className="size-2.5 rounded-[0.125rem] border bg-muted" aria-hidden="true" />
              <span className="size-2.5 rounded-[0.125rem] border border-success/30 bg-success/30" aria-hidden="true" />
              <span className="size-2.5 rounded-[0.125rem] border border-success/60 bg-success/60" aria-hidden="true" />
              <span className="size-2.5 rounded-[0.125rem] bg-success" aria-hidden="true" />
              <span>More</span>
            </span>
          </div>
        </div>
      </section>

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border bg-card p-6" aria-labelledby="prep-heading">
          <p className="text-xs font-semibold uppercase tracking-[0.0078rem] text-muted-foreground">Prep path</p>
          <h2 id="prep-heading" className="mt-2 text-xl font-semibold tracking-[-0.008rem]">
            {prepPath ? PREP_PATH_NAMES[prepPath] : 'Choose your direction'}
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {prepPath
              ? 'Your recommendations follow this path.'
              : 'Pick a path to get a focused challenge sequence.'}
          </p>
          <Link to="/challenges" className="mt-5 inline-flex text-sm font-semibold text-primary hover:underline">
            {prepPath ? 'Change prep path' : 'Choose a prep path'} →
          </Link>
        </section>

        <section className="rounded-lg border bg-card p-6" aria-labelledby="continue-heading">
          <p className="text-xs font-semibold uppercase tracking-[0.0078rem] text-muted-foreground">
            {next?.progress.status === 'attempted' ? 'Continue' : 'Up next'}
          </p>
          <h2 id="continue-heading" className="mt-2 text-xl font-semibold tracking-[-0.008rem]">
            {next?.title ?? 'All challenges complete'}
          </h2>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">
            {next?.blurb ?? 'You have completed the current catalog.'}
          </p>
          {next && (
            <Link
              to={`/c/${continueSlug(next)}`}
              className={`${buttonVariants({ variant: 'primary', size: 'sm' })} mt-5`}
            >
              Open challenge
            </Link>
          )}
        </section>
      </div>
    </main>
  )
}

export default function Profile() {
  if (!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY) {
    return <Navigate to="/challenges" replace />
  }
  return <ConfiguredProfile />
}
