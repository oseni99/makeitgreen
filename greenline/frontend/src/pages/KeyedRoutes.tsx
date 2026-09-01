import { useParams } from 'react-router-dom'
import Solution from './Solution'
import Workspace from './Workspace'

export function WorkspaceRoute() {
  const { slug = '' } = useParams()
  return <Workspace key={slug} />
}

export function SolutionRoute() {
  const { slug = '' } = useParams()
  return <Solution key={slug} />
}
