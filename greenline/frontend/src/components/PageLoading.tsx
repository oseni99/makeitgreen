export function PageLoading({ label }: { label: string }) {
  return (
    <div
      className="grid min-h-[calc(100svh-4rem)] place-items-center bg-background px-6 py-16"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <span
          className="size-4 animate-spin rounded-full border-2 border-border border-t-foreground"
          aria-hidden="true"
        />
        <span>{label}</span>
      </div>
    </div>
  )
}
