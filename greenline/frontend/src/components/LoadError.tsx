import { AlertTriangle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function LoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <section
      className="mx-auto my-24 max-w-lg rounded-xl border bg-card p-6 sm:p-8"
      aria-labelledby="load-error-title"
    >
      <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.01em] text-destructive">
        <AlertTriangle className="size-4" aria-hidden="true" />
        <span>COULD NOT LOAD</span>
      </div>
      <h1
        id="load-error-title"
        className="mt-5 text-[1.625rem] font-bold leading-[1.23] tracking-[-0.039rem]"
      >
        We couldn’t load this page.
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        Check your connection and try again. Your saved challenge work is still safe.
      </p>
      <Button type="button" variant="primary" size="sm" className="mt-6" onClick={onRetry}>
        <RefreshCw className="size-4" aria-hidden="true" />
        Retry
      </Button>
    </section>
  )
}
