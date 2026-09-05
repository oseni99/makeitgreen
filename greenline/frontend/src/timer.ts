export type TimerStatus = 'idle' | 'running' | 'paused' | 'complete'

export interface TimerState {
  durationMinutes: number
  accumulatedMs: number
  status: TimerStatus
  startedAt?: number
}

const MIN_MINUTES = 1
const MAX_MINUTES = 180
const key = (slug: string) => `greenline-timer-${slug}`

function validMinutes(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= MIN_MINUTES &&
    value <= MAX_MINUTES
  )
}

function isTimerState(value: unknown): value is TimerState {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<TimerState>
  const startedAtValid =
    candidate.startedAt === undefined ||
    (typeof candidate.startedAt === 'number' &&
      Number.isFinite(candidate.startedAt) &&
      candidate.startedAt >= 0)
  return (
    validMinutes(candidate.durationMinutes) &&
    typeof candidate.accumulatedMs === 'number' &&
    Number.isFinite(candidate.accumulatedMs) &&
    candidate.accumulatedMs >= 0 &&
    ['idle', 'running', 'paused', 'complete'].includes(candidate.status ?? '') &&
    startedAtValid &&
    (candidate.status === 'running' ? candidate.startedAt !== undefined : true)
  )
}

function freshTimer(suggestedMinutes: number): TimerState {
  return {
    durationMinutes: validMinutes(suggestedMinutes) ? suggestedMinutes : 25,
    accumulatedMs: 0,
    status: 'idle',
  }
}

function persist(slug: string, state: TimerState): TimerState {
  try {
    localStorage.setItem(key(slug), JSON.stringify(state))
  } catch {
    // Storage can be disabled or full; timing should not prevent the workspace loading.
  }
  return state
}

function migrateLegacyTimer(value: unknown, suggestedMinutes: number): TimerState | null {
  if (!value || typeof value !== 'object') return null
  const legacy = value as { startedAt?: unknown; stoppedElapsed?: unknown }
  if (
    typeof legacy.startedAt !== 'number' ||
    !Number.isFinite(legacy.startedAt) ||
    legacy.startedAt < 0
  ) {
    return null
  }
  const stopped = legacy.stoppedElapsed
  if (typeof stopped === 'number' && Number.isFinite(stopped) && stopped >= 0) {
    return {
      ...freshTimer(suggestedMinutes),
      accumulatedMs: stopped,
      status: 'complete',
    }
  }
  return {
    ...freshTimer(suggestedMinutes),
    accumulatedMs: Math.max(0, Date.now() - legacy.startedAt),
    status: 'paused',
  }
}

export function loadTimer(slug: string, suggestedMinutes: number): TimerState {
  try {
    const raw = localStorage.getItem(key(slug))
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (isTimerState(parsed)) return parsed
      const migrated = migrateLegacyTimer(parsed, suggestedMinutes)
      if (migrated) return persist(slug, migrated)
    }
  } catch {
    // Corrupted or unavailable storage starts with an idle timer.
  }
  return persist(slug, freshTimer(suggestedMinutes))
}

export function setTimerDuration(
  slug: string,
  state: TimerState,
  durationMinutes: number,
): TimerState {
  if (!validMinutes(durationMinutes)) return state
  return persist(slug, {
    durationMinutes,
    accumulatedMs: 0,
    status: 'idle',
  })
}

export function startTimer(slug: string, state: TimerState): TimerState {
  if (state.status === 'running' || state.status === 'complete') return state
  return persist(slug, {
    ...state,
    status: 'running',
    startedAt: Date.now(),
  })
}

export function pauseTimer(slug: string, state: TimerState): TimerState {
  if (state.status !== 'running') return state
  return persist(slug, {
    durationMinutes: state.durationMinutes,
    accumulatedMs: elapsedMs(state),
    status: 'paused',
  })
}

export function stopTimer(
  slug: string,
  state: TimerState,
  finalElapsed?: number,
): TimerState {
  if (state.status === 'idle' || state.status === 'complete') return state
  return persist(slug, {
    durationMinutes: state.durationMinutes,
    accumulatedMs: finalElapsed ?? elapsedMs(state),
    status: 'complete',
  })
}

export function clearTimer(slug: string, suggestedMinutes: number): TimerState {
  try {
    localStorage.removeItem(key(slug))
  } catch {
    // Continue with an in-memory idle timer when storage is unavailable.
  }
  return persist(slug, freshTimer(suggestedMinutes))
}

export function elapsedMs(state: TimerState): number {
  if (state.status !== 'running' || state.startedAt === undefined) {
    return state.accumulatedMs
  }
  return state.accumulatedMs + Math.max(0, Date.now() - state.startedAt)
}

export function formatClock(ms: number): string {
  const total = Math.floor(Math.abs(ms) / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
