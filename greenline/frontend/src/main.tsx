import { StrictMode } from 'react'
import '@fontsource-variable/inter'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App'
import Landing from './pages/Landing'
import Catalog from './pages/Catalog'
import { SolutionRoute, WorkspaceRoute } from './pages/KeyedRoutes'
import './styles/globals.css'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Landing /> },
      { path: 'challenges', element: <Catalog /> },
      { path: 'c/:slug', element: <WorkspaceRoute /> },
      { path: 'c/:slug/solution', element: <SolutionRoute /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
