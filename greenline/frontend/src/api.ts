export interface Progress {
  status: 'todo' | 'attempted' | 'solved'
  attempts: number
  spoiled?: boolean
}

export interface ChallengeMeta {
  slug: string
  title: string
  type: string
  difficulty: string
  minutes: number
  language: string
  blurb: string
  brief: string
  progress: Progress
  creatable?: string[]
}

export interface FileEntry {
  path: string
  readonly: boolean
  edited: boolean
  new?: boolean
}

export interface ChallengeDetail extends ChallengeMeta {
  files: FileEntry[]
}

export interface TestCase {
  id: string
  outcome: 'passed' | 'failed' | 'error' | 'skipped' | 'xfailed' | 'xpassed' | 'unknown'
  duration_ms: number
  file: string | null
  line: number | null
  message: string
  crash_file: string | null
  crash_line: number | null
}

export interface RunMeta {
  id: number
  slug: string
  started_at: string
  duration_ms: number
  session_elapsed_ms: number | null
  green: boolean
  passed: number
  failed: number
  errors: number
  skipped: number
  exit_code: number
}

export interface RunResult {
  exit_code: number
  green: boolean
  output: string
  /** True when the backend truncated pytest output to the last 20k chars. */
  output_truncated?: boolean
  tests: TestCase[]
  passed: number
  failed: number
  errors: number
  skipped: number
  duration_ms?: number
  run?: RunMeta
}

export interface RunHistoryEntry extends RunMeta {
  output_tail: string
  output_truncated: boolean
  tests: TestCase[]
}

export interface RunJobStart {
  job_id: string
  slug: string
  status: 'queued'
}

export interface RunJobSnapshot {
  job_id: string
  slug: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  output: string
  next_offset: number
  output_truncated?: boolean
  result?: RunResult
  error?: string
}

export interface SolutionFile {
  path: string
  content: string
  original: string
}

export interface Solution {
  writeup: string
  files: SolutionFile[]
}

export interface SearchHit {
  path: string
  line: number
  text: string
}

export type FetchOpts = { signal?: AbortSignal }

export class ApiError extends Error {
  readonly status: number

  constructor(method: string, url: string, status: number) {
    super(`${method} ${url} → ${status}`)
    this.name = 'ApiError'
    this.status = status
  }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const token = await getAuthToken()
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const r = await fetch(url, { ...init, headers })
  if (!r.ok) throw new ApiError(init?.method ?? 'GET', url, r.status)
  return r.json()
}

/** True when fetch was canceled via AbortController (StrictMode remount, nav). */
export function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (err instanceof Error && err.name === 'AbortError')
  )
}

export function isNotFoundError(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 404
}

export function fileUrl(slug: string, path: string): string {
  const encodedPath = path.split('/').map(encodeURIComponent).join('/')
  return `/api/challenges/${encodeURIComponent(slug)}/files/${encodedPath}`
}

export const api = {
  listChallenges: (opts?: FetchOpts) =>
    req<{ challenges: ChallengeMeta[] }>('/api/challenges', { signal: opts?.signal }).then(
      (d) => d.challenges,
    ),
  getChallenge: (slug: string, opts?: FetchOpts) =>
    req<ChallengeDetail>(`/api/challenges/${slug}`, { signal: opts?.signal }),
  getFile: (slug: string, path: string, opts?: FetchOpts) =>
    req<{ content: string }>(fileUrl(slug, path), { signal: opts?.signal }).then(
      (d) => d.content,
    ),
  saveFile: (slug: string, path: string, content: string) =>
    req(fileUrl(slug, path), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }),
  createFile: (slug: string, path: string, content = '') =>
    req<{ ok: boolean; path: string; new: boolean }>(fileUrl(slug, path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }),
  deleteFile: (slug: string, path: string) =>
    req(fileUrl(slug, path), { method: 'DELETE' }),
  runTests: (slug: string, sessionElapsedMs?: number) =>
    req<RunResult>(`/api/challenges/${slug}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_elapsed_ms: sessionElapsedMs ?? null,
      }),
    }),
  startRun: (slug: string, sessionElapsedMs?: number) =>
    req<RunJobStart>(`/api/challenges/${slug}/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_elapsed_ms: sessionElapsedMs ?? null,
      }),
    }),
  getRunJob: (jobId: string, after = 0) =>
    req<RunJobSnapshot>(`/api/run-jobs/${encodeURIComponent(jobId)}?after=${after}`),
  listRuns: (slug: string, opts?: FetchOpts) =>
    req<{ runs: RunHistoryEntry[] }>(`/api/challenges/${slug}/runs`, {
      signal: opts?.signal,
    }).then((d) => d.runs),
  search: (slug: string, q: string) =>
    req<{ hits: SearchHit[] }>(
      `/api/challenges/${slug}/search?q=${encodeURIComponent(q)}`,
    ).then((d) => d.hits),
  reset: (slug: string) => req(`/api/challenges/${slug}/reset`, { method: 'POST' }),
  spoil: (slug: string) =>
    req<{ ok: true; progress: Progress }>(`/api/challenges/${slug}/spoil`, { method: 'POST' }),
  getSolution: (slug: string, opts?: FetchOpts) =>
    req<Solution>(`/api/challenges/${slug}/solution`, { signal: opts?.signal }),
}
import { getAuthToken } from './authToken.ts'
