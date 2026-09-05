import { SignIn, useAuth } from '@clerk/react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { setAuthTokenProvider } from './authToken'
import { signInAppearance } from './clerkAppearance'

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
    <main className="min-h-[calc(100svh-4rem)] bg-muted/50 px-6 py-12 md:px-10 md:py-20">
      <div className="mx-auto grid max-w-[960px] items-center gap-10 md:grid-cols-[1fr_26rem] md:gap-16">
        <section aria-labelledby="sign-in-page-heading">
          <p className="text-xs font-semibold uppercase tracking-[0.0078rem] text-primary">
            Production backend practice
          </p>
          <h1
            id="sign-in-page-heading"
            className="mt-3 max-w-xl text-[2.5rem] font-bold leading-[1.1] tracking-[-0.025em] md:text-[3.375rem]"
          >
            Get back to making it green.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
            Debug realistic repositories, run the tests, and build the judgment backend interviews actually measure.
          </p>
          <p className="mt-6 text-sm font-medium text-foreground">
            Real repositories <span className="mx-2 text-border" aria-hidden="true">·</span> Python + JavaScript
          </p>
        </section>

        <section
          className="w-full"
          aria-label="Sign in to MakeItGreen"
        >
          <SignIn
            routing="path"
            path="/sign-in"
            fallbackRedirectUrl="/challenges"
            appearance={signInAppearance}
          />
        </section>
      </div>
    </main>
  )
}
