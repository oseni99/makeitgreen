import { ArrowRight, LogOut } from 'lucide-react'
import { useClerk, useUser } from '@clerk/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api, isAbortError, type ChallengeSummary, type LearnerPreferences } from '../api'
import { LoadError } from '../components/LoadError'
import { PageLoading } from '../components/PageLoading'
import { PREP_TRACKS } from '../prepPaths'
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

function ConfiguredProfile() {
  const { isLoaded, isSignedIn, user } = useUser()
  const { signOut } = useClerk()
  const [challenges, setChallenges] = useState<ChallengeSummary[] | null>(null)
  const [preferences, setPreferences] = useState<LearnerPreferences | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [items, learnerPreferences] = await Promise.all([
        api.listChallenges({ signal }),
        api.getPreferences({ signal }),
      ])
      if (signal?.aborted) return
      setChallenges(items)
      setPreferences(learnerPreferences)
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
    }
  }, [challenges])

  if (error) {
    return (
      <LoadError
        onRetry={() => {
          setError(false)
          setChallenges(null)
          setPreferences(null)
          void load()
        }}
      />
    )
  }
  if (!isLoaded || !challenges || !preferences) {
    return <PageLoading label="Loading profile…" />
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
  const nextVariant =
    next?.variants?.find((variant) => variant.progress.status === 'attempted') ??
    next?.variants?.find((variant) => variant.progress.status === 'todo')

  return (
    <main className="mx-auto max-w-[920px] px-6 py-14 md:px-10 md:py-20">
      <div className="flex flex-wrap items-center gap-4">
        <img className="size-16 rounded-full object-cover" src={user.imageUrl} alt="" />
        <div className="min-w-0">
          <h1 className="truncate text-[clamp(2rem,5vw,2.5rem)] font-bold leading-[1.1] tracking-[-0.025em]">
            {name}
          </h1>
          {email && <p className="mt-1 truncate text-sm text-muted-foreground">{email}</p>}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto text-muted-foreground hover:text-foreground"
          onClick={() => void signOut({ redirectUrl: '/' })}
        >
          <LogOut className="size-4" aria-hidden="true" />
          Sign out
        </Button>
      </div>

      <div className="mt-12 grid gap-4 md:grid-cols-[minmax(0,1fr)_18rem] md:items-start">
        <section className="rounded-lg border bg-card p-6" aria-labelledby="continue-heading">
          <h2
            id="continue-heading"
            className="text-xs font-semibold uppercase tracking-[0.0078rem] text-muted-foreground"
          >
            {next?.progress.status === 'attempted' ? 'Continue practicing' : 'Up next'}
          </h2>
          <h3 className="mt-3 text-[1.625rem] font-bold leading-[1.23] tracking-[-0.039rem]">
            {next?.title ?? 'All challenges complete'}
          </h3>
          <p className="mt-2 line-clamp-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            {next?.blurb ?? 'You have completed the current catalog.'}
          </p>
          {next && (
            <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
                <span>{next.type}</span>
                <span aria-hidden="true">·</span>
                <span>{next.difficulty}</span>
                <span aria-hidden="true">·</span>
                <span>{nextVariant?.language ?? next.language}</span>
                <span aria-hidden="true">·</span>
                <span>~{next.minutes} min</span>
              </div>
              <Link
                to={`/c/${continueSlug(next)}`}
                className={`${buttonVariants({ variant: 'primary' })} shrink-0`}
              >
                Open challenge
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </div>
          )}
        </section>

        <section className="rounded-lg border bg-card p-6" aria-labelledby="progress-heading">
          <h2
            id="progress-heading"
            className="text-xs font-semibold uppercase tracking-[0.0078rem] text-muted-foreground"
          >
            Progress
          </h2>
          <div className="mt-5 grid grid-cols-2 gap-4">
            {[
              ['Completed', progress.solved],
              ['In progress', progress.attempted],
            ].map(([label, value]) => (
              <div key={label} role="group" aria-label={`${value} ${label.toString().toLowerCase()}`}>
                <p className="text-2xl font-bold tracking-tight">{value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>
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
