import { StrictMode } from 'react'
import '@fontsource-variable/inter'
import { ClerkProvider } from '@clerk/react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App'
import { AuthBridge, RouteGate, SignInPage } from './auth'
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
      { path: 'sign-in/*', element: <SignInPage /> },
      {
        element: <RouteGate />,
        children: [
          { path: 'challenges', element: <Catalog /> },
          { path: 'c/:slug', element: <WorkspaceRoute /> },
          { path: 'c/:slug/solution', element: <SolutionRoute /> },
        ],
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ? (
      <ClerkProvider publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY}>
        <AuthBridge />
        <RouterProvider router={router} />
      </ClerkProvider>
    ) : (
      <RouterProvider router={router} />
    )}
  </StrictMode>,
)
