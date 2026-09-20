import { lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'

import { PageLoading } from '../components/PageLoading'

const Workspace = lazy(async () => {
  const [, route] = await Promise.all([import('../monacoSetup'), import('./Workspace')])
  return route
})

const Solution = lazy(async () => {
  const [, route] = await Promise.all([import('../monacoSetup'), import('./Solution')])
  return route
})

export function WorkspaceRoute() {
  const { slug = '' } = useParams()
  return (
    <Suspense fallback={<PageLoading label="Opening workspace…" />}>
      <Workspace key={slug} />
    </Suspense>
  )
}

export function SolutionRoute() {
  const { slug = '' } = useParams()
  return (
    <Suspense fallback={<PageLoading label="Loading solution…" />}>
      <Solution key={slug} />
    </Suspense>
  )
}
