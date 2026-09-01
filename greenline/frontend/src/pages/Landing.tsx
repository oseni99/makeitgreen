import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, isAbortError } from '../api'
import { buttonVariants } from '@/components/ui/button-variants'

const TYPES = [
  {
    name: 'Concurrency',
    desc: 'Races, deadlocks, and locking bugs that only show up when requests collide.',
    accent: 'bg-sticker-purple',
  },
  {
    name: 'Repository Implementation',
    desc: 'Implement and fix real backend features — bookings, payments, wallets — inside an existing codebase.',
    accent: 'bg-sticker-sky',
  },
  {
    name: 'API Contract Debugging',
    desc: 'Wrong statuses, broken idempotency, leaky errors — fix the handler until the contract holds.',
    accent: 'bg-sticker-pink',
  },
  {
    name: 'Incident Debugging',
    desc: 'A service crashed in production. Read the logs, find the root cause, bring it back green.',
    accent: 'bg-sticker-orange',
  },
  {
    name: 'Architecture Extension',
    desc: 'Extend a working service to support a new feature under interview constraints.',
    accent: 'bg-sticker-teal',
  },
  {
    name: 'Database Engineering',
    desc: 'Transactions, indexing, migrations, and consistency failures against real invariants.',
    accent: 'bg-sticker-green',
  },
  {
    name: 'Runtime Diagnostics',
    desc: 'Read profiler, heap, and thread evidence to fix latency, starvation, and memory pressure.',
    accent: 'bg-sticker-purple',
  },
]

export default function Landing() {
  const [liveTypes, setLiveTypes] = useState<Set<string> | null>(null)

  useEffect(() => {
    const ac = new AbortController()
    api
      .listChallenges({ signal: ac.signal })
      .then((challenges) => setLiveTypes(new Set(challenges.map((c) => c.type))))
      .catch((err) => {
        if (!isAbortError(err)) setLiveTypes(new Set())
      })
    return () => ac.abort()
  }, [])

  return (
    <>
      <header className="bg-secondary text-secondary-foreground">
        <div className="mx-auto grid max-w-[1240px] gap-12 px-6 py-20 md:px-10 md:py-28 lg:grid-cols-[1.08fr_0.92fr] lg:items-center">
        <div>
          <div className="mb-5 text-xs font-semibold tracking-[0.01em] text-white/70">
            Post-DSA interview prep · Python
          </div>
          <h1 className="max-w-3xl text-[clamp(2.75rem,6vw,4rem)] font-bold leading-none tracking-[-0.033em]">
            You've done LeetCode. Real interviews hand you a <em>broken repo.</em>
          </h1>
          <p className="mt-7 max-w-2xl text-base leading-7 text-white/75 md:text-lg">
            Backend rounds drop you into an unfamiliar codebase and ask you to find the bug
            and make the failing tests green. Practice exactly that — in your browser, in a
            real sandbox, against reviewed solutions.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/challenges" className={buttonVariants({ variant: 'primary' })}>
              Run a real repo →
            </Link>
            <a href="#how" className={buttonVariants({ variant: 'secondary' })}>
              How it works
            </a>
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-white/15 bg-console-surface font-mono text-[13px] shadow-elevated">
          <div className="flex items-center gap-2 border-b border-white/10 bg-white/[0.04] px-4 py-3 text-xs text-white/50">
            <span className="size-2.5 rounded-full bg-window-close" />
            <span className="size-2.5 rounded-full bg-window-minimize" />
            <span className="size-2.5 rounded-full bg-window-expand" />
            <span className="ml-2">orders-service — ./verify.sh</span>
          </div>
          <pre className="overflow-x-auto p-5 leading-6 text-console-foreground">
            <span className="text-white/45">$ ./verify.sh</span>
            {'\n'}
            <span className="text-console-success">PASS</span> test_creates_order{'\n'}
            <span className="text-console-success">PASS</span> test_applies_discount{'\n'}
            <span className="text-console-error">FAIL</span> test_processes_concurrent_checkouts{'\n'}
            {'  '}expected inventory: <span className="text-console-success">0</span>
            {'\n'}
            {'  '}actual inventory:{'   '}
            <span className="text-console-error">-7</span>{' '}
            <span className="text-console-warning">← race condition</span>
            {'\n\n'}
            <span className="text-white/45">2 passed, 1 failed</span>
            {'\n'}
            <span className="text-console-success">Find the bug. Fix it. Make it green.</span>
          </pre>
        </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1160px] px-6 py-20 md:px-10 md:py-28" id="how">
        <h2 className="text-[clamp(2rem,4vw,2.5rem)] font-bold leading-[1.1] tracking-[-0.025em]">How it works</h2>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Every challenge is a production-style repository with failing tests. The format
          changes; the realism doesn't.
        </p>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border bg-card p-6">
            <span className="mb-8 block text-sm font-semibold text-muted-foreground">01</span>
            <strong className="block text-xl tracking-[-0.01em]">Read the failing state</strong>
            <span className="mt-3 block text-sm leading-6 text-muted-foreground">
              Open the workspace, read the repo structure, run the suite, and see exactly
              what's red and why.
            </span>
          </div>
          <div className="rounded-lg border bg-card p-6">
            <span className="mb-8 block text-sm font-semibold text-muted-foreground">02</span>
            <strong className="block text-xl tracking-[-0.01em]">Fix the source</strong>
            <span className="mt-3 block text-sm leading-6 text-muted-foreground">
              Edit the code in a full browser editor. Tests are read-only — they're the
              spec, not the suspect.
            </span>
          </div>
          <div className="rounded-lg border bg-card p-6">
            <span className="mb-8 block text-sm font-semibold text-muted-foreground">03</span>
            <strong className="block text-xl tracking-[-0.01em]">Make it green, then compare</strong>
            <span className="mt-3 block text-sm leading-6 text-muted-foreground">
              Run the full suite in an isolated sandbox, then review a reference solution
              with interview talking points.
            </span>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1160px] px-6 pb-24 md:px-10 md:pb-32">
        <h2 className="text-[clamp(2rem,4vw,2.5rem)] font-bold leading-[1.1] tracking-[-0.025em]">Challenge types</h2>
        <p className="mt-4 text-muted-foreground">One real repo each. Start with the live ones — more shipping regularly.</p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TYPES.map((t) => (
            <div className="relative overflow-hidden rounded-lg border bg-card p-6" key={t.name}>
              <span className={`mb-10 block size-3 rounded-sm ${t.accent}`} aria-hidden="true" />
              {liveTypes?.has(t.name) && (
                <span className="absolute right-4 top-4 rounded-full bg-muted px-2 py-1 text-[11px] font-semibold text-muted-foreground">LIVE</span>
              )}
              <h3 className="text-xl font-bold tracking-[-0.012em]">{t.name}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{t.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="flex flex-col justify-between gap-2 border-t bg-background px-6 py-8 text-sm text-muted-foreground md:flex-row md:px-10">
        <span>MAKEITGREEN — repository-based interview practice</span>
        <span>local-first · your machine, your repos</span>
      </footer>
    </>
  )
}
