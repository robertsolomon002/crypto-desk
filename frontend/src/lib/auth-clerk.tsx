import { ClerkProvider, Show, SignIn, UserButton, useAuth } from '@clerk/react'
import { useEffect, type ReactNode } from 'react'

import { setTokenGetter } from './api'
import type { AuthRootProps } from './auth'

// Clerk (@clerk/react 6, D39): `<Show when="signed-in">` replaced SignedIn/SignedOut, and
// `useAuth().getToken()` returns a fresh session JWT for the backend (Authorization: Bearer).
// Access mode is Invite-only (D29), so the sign-in page offers no open sign-up.

function TokenBridge({ children }: { children: ReactNode }) {
  const { getToken } = useAuth()
  useEffect(() => {
    setTokenGetter(() => getToken())
    return () => setTokenGetter(null)
  }, [getToken])
  return children
}

function SignInPage() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-background p-4">
      <div className="text-center">
        <h1 className="font-mono text-xl font-semibold tracking-tight">Crypto Desk</h1>
        <p className="text-sm text-muted-foreground">Invite-only. Sign in to continue.</p>
      </div>
      <SignIn routing="hash" />
    </div>
  )
}

export default function ClerkAuthRoot({ children }: AuthRootProps) {
  const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
  if (!publishableKey) {
    return (
      <p role="alert" className="p-8 text-center text-sm">
        Sign-in isn&apos;t configured: VITE_CLERK_PUBLISHABLE_KEY is missing from this build.
      </p>
    )
  }
  return (
    <ClerkProvider publishableKey={publishableKey} afterSignOutUrl="/">
      <Show when="signed-out">
        <SignInPage />
      </Show>
      <Show when="signed-in">
        <TokenBridge>{children(<UserButton />)}</TokenBridge>
      </Show>
    </ClerkProvider>
  )
}
