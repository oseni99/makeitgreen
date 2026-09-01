export interface TimerState {
  startedAt: number
  stoppedElapsed?: number
}

const key = (slug: string) => `greenline-timer-${slug}`

function isTimerState(value: unknown): value is TimerState {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<TimerState>
  const startedAt = candidate.startedAt
  if (typeof startedAt !== 'number' || !Number.isFinite(startedAt) || startedAt < 0) return false
  const stoppedElapsed = candidate.stoppedElapsed
  return (
    stoppedElapsed === undefined ||
    (typeof stoppedElapsed === 'number' && Number.isFinite(stoppedElapsed) && stoppedElapsed >= 0)
  )
}

function persist(slug: string, state: TimerState): void {
  try {
    localStorage.setItem(key(slug), JSON.stringify(state))
  } catch {
    // Storage can be disabled or full; timing should not prevent the workspace loading.
  }
}

export function loadTimer(slug: string): TimerState {
  try {
    const raw = localStorage.getItem(key(slug))
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (isTimerState(parsed)) return parsed
    }
  } catch {
    // corrupted state — start fresh
  }
  const fresh: TimerState = { startedAt: Date.now() }
  persist(slug, fresh)
  return fresh
}

export function stopTimer(
  slug: string,
  state: TimerState,
  finalElapsed = Date.now() - state.startedAt,
): TimerState {
  if (state.stoppedElapsed !== undefined) return state
  const stopped: TimerState = { ...state, stoppedElapsed: finalElapsed }
  persist(slug, stopped)
  return stopped
}

export function clearTimer(slug: string): TimerState {
  try {
    localStorage.removeItem(key(slug))
  } catch {
    // Continue with an in-memory fresh timer when storage is unavailable.
  }
  return loadTimer(slug)
}

export function elapsedMs(state: TimerState): number {
  const stoppedElapsed = state.stoppedElapsed
  if (typeof stoppedElapsed === 'number' && Number.isFinite(stoppedElapsed) && stoppedElapsed >= 0) {
    return stoppedElapsed
  }
  const startedAt = state.startedAt
  if (!Number.isFinite(startedAt)) return 0
  return Math.max(0, Date.now() - startedAt)
}

export function formatClock(ms: number): string {
  const total = Math.floor(Math.abs(ms) / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
