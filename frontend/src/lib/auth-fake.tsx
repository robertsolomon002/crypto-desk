import { useEffect } from 'react'

import { setTokenGetter } from './api'
import type { AuthRootProps } from './auth'

// Playwright only (VITE_E2E_FAKE_AUTH=1, D39): a signed-in user without Clerk, so the smoke
// tests run offline against a mocked API. Production builds never include this module (see
// auth.tsx), and the real backend rejects its token anyway.

export const FAKE_TOKEN = 'e2e-fake-token'

export default function FakeAuthRoot({ children }: AuthRootProps) {
  useEffect(() => {
    setTokenGetter(async () => FAKE_TOKEN)
    return () => setTokenGetter(null)
  }, [])
  return children(
    <span
      aria-label="Signed in as the test user"
      className="grid size-7 place-items-center rounded-full bg-muted text-[10px] font-semibold"
    >
      E2E
    </span>,
  )
}
