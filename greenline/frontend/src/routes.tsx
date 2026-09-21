import type { RouteObject } from 'react-router-dom'

import App from './App'
import { RouteGate, SignInPage } from './auth'
import Catalog from './pages/Catalog'
import { SolutionRoute, WorkspaceRoute } from './pages/KeyedRoutes'
import Landing from './pages/Landing'
import Profile from './pages/Profile'
import RouteError from './pages/RouteError'

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    element: <App />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Landing /> },
      { path: 'sign-in/*', element: <SignInPage /> },
      {
        element: <RouteGate />,
        children: [
          { path: 'challenges', element: <Catalog /> },
          { path: 'profile', element: <Profile /> },
          { path: 'c/:slug', element: <WorkspaceRoute /> },
          { path: 'c/:slug/solution', element: <SolutionRoute /> },
        ],
      },
    ],
  },
]
