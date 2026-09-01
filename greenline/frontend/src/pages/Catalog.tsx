import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, isAbortError, type ChallengeMeta } from '../api'
import { LoadError } from '../components/LoadError'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function statusLabel(status: ChallengeMeta['progress']['status']) {
  if (status === 'solved') return '● SOLVED'
  if (status === 'attempted') return '◐ ATTEMPTED'
  return '○ TODO'
}

export default function Catalog() {
  const [challenges, setChallenges] = useState<ChallengeMeta[] | null>(null)
  const [error, setError] = useState(false)
  const [filter, setFilter] = useState('All')

  const load = useCallback((signal?: AbortSignal) => {
    return api
      .listChallenges({ signal })
      .then(setChallenges)
      .catch((err) => {
        if (!isAbortError(err)) setError(true)
      })
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    void load(ac.signal)
    return () => ac.abort()
  }, [load])

  const types = useMemo(
    () => ['All', ...new Set((challenges ?? []).map((c) => c.type))],
    [challenges],
  )
  const shown = (challenges ?? []).filter((c) => filter === 'All' || c.type === filter)

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
        {challenges.length} repos · {challenges.filter((c) => c.progress.status === 'solved').length} solved
      </p>

      <div className="mt-10 flex flex-wrap gap-2">
        {types.map((t) => (
          <Button
            key={t}
            type="button"
            variant={filter === t ? 'primary' : 'utility'}
            size="sm"
            className={filter === t ? 'rounded-full px-4' : 'rounded-full px-4'}
            onClick={() => setFilter(t)}
          >
            {t}
          </Button>
        ))}
      </div>

      <div className="mt-8 grid gap-3">
        {shown.map((c) => (
          <Link
            to={`/c/${c.slug}`}
            className="group rounded-lg border bg-card p-5 transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-black/20 hover:shadow-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            key={c.slug}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-auto min-w-[220px] text-lg font-semibold tracking-[-0.01em]">{c.title}</span>
              <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{c.type}</span>
              <span className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground">{c.difficulty}</span>
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
          </Link>
        ))}
      </div>
    </main>
  )
}
