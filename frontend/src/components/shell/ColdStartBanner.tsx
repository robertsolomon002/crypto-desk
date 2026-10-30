import { useIsFetching, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

// Cloud Run scales to zero (Decision 5), so the first requests after idle can take ~10 s.
// While nothing has loaded yet and requests have been running for SLOW_MS, say why.
export const SLOW_MS = 1500

export function ColdStartBanner() {
  const fetching = useIsFetching()
  const client = useQueryClient()
  const nothingLoaded = client
    .getQueryCache()
    .getAll()
    .every((query) => query.state.dataUpdatedAt === 0)
  const waiting = fetching > 0 && nothingLoaded
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    if (!waiting) return
    const timer = setTimeout(() => setSlow(true), SLOW_MS)
    return () => clearTimeout(timer)
  }, [waiting])

  if (!waiting || !slow) return null
  return (
    <div
      role="status"
      className="border-b bg-warning/15 px-4 py-1.5 text-center text-xs text-foreground"
    >
      Waking up the server… Free hosting sleeps when idle, so the first load takes about 10 seconds.
    </div>
  )
}
