import { AlertTriangle, ArrowRight, Home, RefreshCw } from 'lucide-react'
import { Link, isRouteErrorResponse, useRouteError } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'

export default function RouteError() {
  const error = useRouteError()
  const notFound = isRouteErrorResponse(error) && error.status === 404

  return (
    <main className="grid min-h-screen place-items-center bg-background px-6 py-16">
      <div className="w-full max-w-2xl">
        <Link to="/" className="mb-8 inline-flex text-[15px] font-bold tracking-[-0.025em]">
          MakeItGreen<span className="text-sticker-green">.</span>
        </Link>

        <section
          className="rounded-xl border bg-card p-6 sm:p-8"
          aria-labelledby="route-error-title"
        >
          <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.01em] text-destructive">
            <AlertTriangle className="size-4" aria-hidden="true" />
            <span>{notFound ? '404 · PAGE NOT FOUND' : 'APPLICATION ERROR'}</span>
          </div>

          <h1
            id="route-error-title"
            className="mt-6 max-w-xl text-[clamp(2.5rem,6vw,4rem)] font-bold leading-none tracking-[-0.033em]"
          >
            {notFound ? 'This page does not exist.' : 'Something went wrong.'}
          </h1>
          <p className="mt-5 max-w-lg leading-7 text-muted-foreground">
            {notFound
              ? 'The link may be outdated or incomplete. Your saved challenge work is still safe.'
              : 'We could not load this page. Try again, or return to the challenge catalog.'}
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/challenges" className={buttonVariants({ variant: 'primary' })}>
              Browse challenges
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            <Link to="/" className={buttonVariants({ variant: 'secondary' })}>
              <Home className="size-4" aria-hidden="true" />
              Go home
            </Link>
            {!notFound && (
              <Button variant="ghost" onClick={() => window.location.reload()}>
                <RefreshCw className="size-4" aria-hidden="true" />
                Try again
              </Button>
            )}
          </div>
        </section>

        <p className="mt-5 text-sm text-muted-foreground">
          If this keeps happening, return to the catalog and reopen your challenge.
        </p>
      </div>
    </main>
  )
}
