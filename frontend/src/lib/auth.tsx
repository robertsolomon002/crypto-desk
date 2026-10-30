import { lazy, Suspense, type ReactNode } from 'react'

export interface AuthRootProps {
  /** Renders the signed-in app; gets the user menu element for the top bar. */
  children: (userMenu: ReactNode) => ReactNode
}

// Vite replaces `import.meta.env.VITE_*` at build time, so a normal build drops the fake branch
// and never emits its chunk. vite.config.ts also refuses a fake-auth build that points at a real
// API, and a unit test checks the deploy workflow never sets the flag (D39).
export const FAKE_AUTH = import.meta.env.VITE_E2E_FAKE_AUTH === '1'

const Root = FAKE_AUTH ? lazy(() => import('./auth-fake')) : lazy(() => import('./auth-clerk'))

export function AuthRoot({ children }: AuthRootProps) {
  return (
    <Suspense fallback={null}>
      <Root>{children}</Root>
    </Suspense>
  )
}
