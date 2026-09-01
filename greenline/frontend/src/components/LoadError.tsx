import { Button } from '@/components/ui/button'

export function LoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="mx-auto my-24 max-w-lg rounded-lg border bg-card p-6 text-center shadow-soft">
      <p className="mb-4 text-sm text-muted-foreground">
        Backend unreachable — is uvicorn running on :8000?
      </p>
      <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}
