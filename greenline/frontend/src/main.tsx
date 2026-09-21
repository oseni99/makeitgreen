import { StrictMode } from 'react'
import '@fontsource-variable/inter'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-600.css'
import { ClerkProvider } from '@clerk/react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { AuthBridge } from './auth'
import { clerkAppearance } from './clerkAppearance'
import { appRoutes } from './routes'
import './styles/globals.css'

const router = createBrowserRouter(appRoutes)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ? (
      <ClerkProvider
        publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY}
        appearance={clerkAppearance}
        signInUrl="/sign-in"
        signInFallbackRedirectUrl="/challenges"
        signUpFallbackRedirectUrl="/challenges"
      >
        <AuthBridge />
        <RouterProvider router={router} />
      </ClerkProvider>
    ) : (
      <RouterProvider router={router} />
    )}
  </StrictMode>,
)
