export interface TimerState {
  startedAt: number
  stoppedElapsed?: number
}

const key = (slug: string) => `greenline-timer-${slug}`

export function loadTimer(slug: string): TimerState {
  try {
    const raw = localStorage.getItem(key(slug))
    if (raw) return JSON.parse(raw) as TimerState
  } catch {
    // corrupted state — start fresh
  }
  const fresh: TimerState = { startedAt: Date.now() }
  localStorage.setItem(key(slug), JSON.stringify(fresh))
  return fresh
}

export function stopTimer(
  slug: string,
  state: TimerState,
  finalElapsed = Date.now() - state.startedAt,
): TimerState {
  if (state.stoppedElapsed !== undefined) return state
  const stopped: TimerState = { ...state, stoppedElapsed: finalElapsed }
  localStorage.setItem(key(slug), JSON.stringify(stopped))
  return stopped
}

export function clearTimer(slug: string): TimerState {
  localStorage.removeItem(key(slug))
  return loadTimer(slug)
}

export function elapsedMs(state: TimerState): number {
  return state.stoppedElapsed ?? Date.now() - state.startedAt
}

export function formatClock(ms: number): string {
  const total = Math.floor(Math.abs(ms) / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
