import { SignIn, useAuth } from '@clerk/react'
import { shadcn } from '@clerk/ui/themes'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { setAuthTokenProvider } from './authToken'

export function AuthBridge() {
  const { getToken } = useAuth()

  useEffect(() => {
    setAuthTokenProvider(() => getToken())
    return () => setAuthTokenProvider(null)
  }, [getToken])

  return null
}

export function ProtectedRoute() {
  const { isLoaded, isSignedIn } = useAuth()
  const location = useLocation()

  if (!isLoaded) return <div className="py-32 text-center text-sm text-muted-foreground">Loading account…</div>
  if (!isSignedIn) {
    const returnTo = `${location.pathname}${location.search}`
    return <Navigate to={`/sign-in?redirect_url=${encodeURIComponent(returnTo)}`} replace />
  }
  return <Outlet />
}

export function RouteGate() {
  if (!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY) return <Outlet />
  return <ProtectedRoute />
}

export function SignInPage() {
  return (
    <main className="flex min-h-[calc(100svh-4rem)] items-center justify-center bg-background px-6 py-12">
      <SignIn
        routing="path"
        path="/sign-in"
        fallbackRedirectUrl="/challenges"
        appearance={{
          theme: shadcn,
          variables: { colorPrimary: '#0075de', borderRadius: '0.5rem' },
        }}
      />
    </main>
  )
}
